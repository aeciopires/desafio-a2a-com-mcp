"""Booking use cases on top of the repository: what the MCP tools call."""

from __future__ import annotations

from dataclasses import dataclass

from mcp_server import domain, metrics
from mcp_server.domain import DomainError, Reservation, Room, ValidRequest
from mcp_server.repository import Repository
from mcp_server.telemetry import tracer


@dataclass(frozen=True)
class Availability:
    room: Room
    free: bool
    conflicts: list[Reservation]


class BookingService:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository
        self.policy_version = domain.parse_policy_version(repository.policy_text)
        for room_id in repository.rooms:
            metrics.RESERVATIONS_ACTIVE.labels(room=room_id).set(0)
        for reservation in repository.reservations():
            metrics.RESERVATIONS_ACTIVE.labels(room=reservation.sala).inc()

    @property
    def policy_text(self) -> str:
        return self.repository.policy_text

    def rooms(self) -> list[Room]:
        return list(self.repository.rooms.values())

    def validate(self, tool: str, room_id: str, inicio: str, fim: str) -> ValidRequest:
        with tracer.start_as_current_span("domain.validate") as span:
            span.set_attribute("room.id", room_id)
            try:
                return domain.validate_request(self.repository.rooms, room_id, inicio, fim)
            except DomainError as exc:
                span.set_attribute("domain.error", exc.reason)
                metrics.MCP_TOOL_ERRORS.labels(tool=tool, reason=exc.reason).inc()
                raise

    def availability(self, tool: str, room_id: str, inicio: str, fim: str) -> Availability:
        request = self.validate(tool, room_id, inicio, fim)
        found = domain.conflicts(self.repository.reservations(), request.room.id, request.start, request.end)
        return Availability(room=request.room, free=not found, conflicts=found)

    def alternatives(self, tool: str, request: ValidRequest) -> list[str]:
        """Alternative rooms for a conflicting request; raises when there is none."""
        with tracer.start_as_current_span("domain.alternatives") as span:
            found = domain.alternatives(
                self.repository.rooms, self.repository.reservations(), request.room, request.start, request.end
            )
            # A string, not a list: Grafana's Jaeger datasource drops array attributes.
            span.set_attribute("mrtr.alternatives", ", ".join(found))
            if not found:
                metrics.MCP_TOOL_ERRORS.labels(tool=tool, reason="sem_alternativas").inc()
                raise DomainError("sem_alternativas", domain.MSG_NO_ALTERNATIVES)
            return found

    def reserve(self, room_id: str, inicio: str, fim: str, responsavel: str) -> Reservation:
        reservation = self.repository.add(room_id, inicio, fim, responsavel)
        metrics.RESERVATIONS_CREATED.labels(
            room=room_id,
            responsible=responsavel,
            date=reservation.start.astimezone(domain.POLICY_TZ).date().isoformat(),
        ).inc(exemplar=metrics.exemplar())
        metrics.RESERVATIONS_ACTIVE.labels(room=room_id).inc()
        return reservation
