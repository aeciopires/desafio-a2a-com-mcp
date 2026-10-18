"""MCP tools and resource, built on the official SDK (MCPServer, 2026-07-28).

MRTR is expressed the SDK way: `reservar_sala` takes a parameter resolved by
`escolha_de_sala`. When the requested room is busy the resolver returns an
`Elicit` marker, and the SDK answers the `tools/call` with `input_required`
(elicitation in form mode + sealed `requestState`) instead of running the tool
body. The retry brings `inputResponses`/`requestState`; the SDK's
`RequestStateBoundary` verifies the seal (AES-256-GCM, TTL, binding to the
original arguments) before any of this code runs, so the tool only ever sees
state it minted. Nothing is kept in memory between the two rounds.
"""

from __future__ import annotations

from typing import Annotated, Literal

from mcp.server.elicitation import AcceptedElicitation, DeclinedElicitation, ElicitationResult
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.resolve import Elicit, Resolve
from mcp.server.request_state import RequestStateSecurity
from pydantic import BaseModel, Field, create_model

from mcp_server.config import SERVER_NAME, Settings
from mcp_server.domain import DomainError
from mcp_server.service import BookingService

POLICY_URI = "politica://uso"
ELICITATION_MESSAGE = "A sala pedida esta ocupada nesse intervalo. Escolha uma alternativa."

# Output models. Their names and fields are part of the wire contract (exemplos/wire/01-tools-list.json).


class SalaOut(BaseModel):
    id: str
    nome: str
    capacidade: int
    recursos: list[str]


class ListaDeSalas(BaseModel):
    salas: list[SalaOut]


class ConflitoOut(BaseModel):
    id: str
    inicio: str
    fim: str
    responsavel: str


class Disponibilidade(BaseModel):
    sala: str
    livre: bool
    conflitos: list[ConflitoOut]


class ReservaOut(BaseModel):
    reserva: str | None = None
    reservado: bool = True
    sala: str | None = None
    inicio: str | None = None
    fim: str | None = None
    responsavel: str | None = None
    politica: str | None = None
    motivo: str | None = None


class RoomChoice(BaseModel):
    """Base shape of the elicitation answer; the live schema narrows `sala` to the alternatives."""

    sala: str


_service: BookingService | None = None


def _svc() -> BookingService:
    if _service is None:
        raise RuntimeError("BookingService not initialised; call build_server() first")
    return _service


def _choice_schema(options: list[str]) -> type[RoomChoice]:
    """Flat schema whose only property is `sala`, restricted to `options` (enum, or const for one)."""
    return create_model(
        "EscolhaDeSala",
        __base__=RoomChoice,
        sala=(Literal[tuple(options)], Field(title="Sala", description="Sala alternativa escolhida")),
    )


def escolha_de_sala(sala: str, inicio: str, fim: str) -> Elicit[RoomChoice] | None:
    """Resolver: decides whether `reservar_sala` needs the user to pick another room.

    Returns None when the requested room is free. On a conflict it returns an
    `Elicit` with the alternatives; on the retry round the SDK matches the answer
    to this same question and injects it into the tool. Raising `ToolError` here
    becomes an `isError: true` result with the exact domain message.
    """
    service = _svc()
    try:
        availability = service.availability("reservar_sala", sala, inicio, fim)
        if availability.free:
            return None
        request = service.validate("reservar_sala", sala, inicio, fim)
        options = service.alternatives("reservar_sala", request)
    except DomainError as exc:
        raise ToolError(exc.message) from exc
    return Elicit(ELICITATION_MESSAGE, _choice_schema(options))


def build_server(settings: Settings, service: BookingService) -> MCPServer:
    global _service
    _service = service

    server = MCPServer(
        SERVER_NAME,
        version=settings.version,
        request_state_security=RequestStateSecurity(
            keys=[settings.request_state_secret],
            ttl=float(settings.request_state_ttl),
            # No authentication in this challenge, so there is no principal to bind.
            bind_principal=None,
        ),
    )

    @server.tool(description="Lista todas as salas com capacidade e recursos.")
    def listar_salas() -> ListaDeSalas:
        return ListaDeSalas(
            salas=[
                SalaOut(id=r.id, nome=r.nome, capacidade=r.capacidade, recursos=list(r.recursos))
                for r in service.rooms()
            ]
        )

    @server.tool(description="Diz se uma sala esta livre no intervalo, e quais reservas conflitam.")
    def consultar_disponibilidade(sala: str, inicio: str, fim: str) -> Disponibilidade:
        try:
            availability = service.availability("consultar_disponibilidade", sala, inicio, fim)
        except DomainError as exc:
            raise ToolError(exc.message) from exc
        return Disponibilidade(
            sala=availability.room.id,
            livre=availability.free,
            conflitos=[
                ConflitoOut(id=r.id, inicio=r.inicio, fim=r.fim, responsavel=r.responsavel)
                for r in availability.conflicts
            ],
        )

    @server.tool(description="Reserva uma sala. Se o intervalo estiver ocupado, pergunta qual alternativa usar.")
    def reservar_sala(
        sala: str,
        inicio: str,
        fim: str,
        responsavel: str,
        escolha: Annotated[ElicitationResult[RoomChoice], Resolve(escolha_de_sala)],
    ) -> ReservaOut:
        if isinstance(escolha, DeclinedElicitation):
            return ReservaOut(reservado=False, motivo="recusado")
        if not isinstance(escolha, AcceptedElicitation):
            return ReservaOut(reservado=False, motivo="cancelado")
        # `data` is None when the room was free; otherwise it is the validated choice.
        room_id = escolha.data.sala if escolha.data is not None else sala
        reservation = service.reserve(room_id, inicio, fim, responsavel)
        return ReservaOut(
            reserva=reservation.id,
            reservado=True,
            sala=reservation.sala,
            inicio=reservation.inicio,
            fim=reservation.fim,
            responsavel=reservation.responsavel,
            politica=service.policy_version,
        )

    @server.resource(
        POLICY_URI,
        name="politica-de-uso",
        description="Politica de uso das salas. A primeira linha declara a versao.",
        mime_type="text/markdown",
    )
    def politica_de_uso() -> str:
        return service.policy_text

    return server
