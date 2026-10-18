from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
import respx

MCP_URL = "http://mcp.test/mcp"
REQUEST_STATE = "v1.SEALED-OPAQUE-STATE-THAT-MUST-NEVER-LEAK-0123456789abcdef"
INPUT_KEY = "mcp_server.server:escolha_de_sala"
POLICY = "versao: 2026-11-01\n\n- regra\n"


def complete(structured: dict[str, Any]) -> dict[str, Any]:
    return {
        "resultType": "complete",
        "isError": False,
        "content": [{"type": "text", "text": json.dumps(structured)}],
        "structuredContent": structured,
    }


def booked(sala: str, reserva: str = "res-0003") -> dict[str, Any]:
    return complete(
        {
            "reserva": reserva,
            "reservado": True,
            "sala": sala,
            "inicio": "2026-11-03T14:00:00-03:00",
            "fim": "2026-11-03T15:00:00-03:00",
            "responsavel": "Marty",
            "politica": "2026-11-01",
            "motivo": None,
        }
    )


def input_required(options: list[str]) -> dict[str, Any]:
    prop: dict[str, Any] = {"type": "string", "title": "Sala"}
    if len(options) == 1:
        prop["const"] = options[0]
    else:
        prop["enum"] = options
    return {
        "resultType": "input_required",
        "inputRequests": {
            INPUT_KEY: {
                "method": "elicitation/create",
                "params": {
                    "mode": "form",
                    "message": "A sala pedida esta ocupada nesse intervalo. Escolha uma alternativa.",
                    "requestedSchema": {"type": "object", "properties": {"sala": prop}, "required": ["sala"]},
                },
            }
        },
        "requestState": REQUEST_STATE,
    }


def tool_error(text: str) -> dict[str, Any]:
    return {"resultType": "complete", "isError": True, "content": [{"type": "text", "text": text}]}


class FakeMcp:
    """Scripted MCP server: records every request and answers `tools/call` from a queue."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.headers: list[httpx.Headers] = []
        self.tool_results: list[dict[str, Any] | tuple[int, dict[str, Any]]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        self.headers.append(request.headers)
        method = body["method"]
        if method == "tools/list":
            result: dict[str, Any] = {
                "resultType": "complete",
                "tools": [
                    {"name": n, "inputSchema": {"type": "object"}}
                    for n in ("listar_salas", "consultar_disponibilidade", "reservar_sala")
                ],
            }
        elif method == "resources/read":
            result = {
                "resultType": "complete",
                "contents": [{"uri": "politica://uso", "mimeType": "text/markdown", "text": POLICY}],
            }
        else:
            scripted = self.tool_results.pop(0)
            if isinstance(scripted, tuple):
                status, error = scripted
                return httpx.Response(status, json={"jsonrpc": "2.0", "id": body["id"], "error": error})
            result = scripted
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

    def calls(self, method: str) -> list[dict[str, Any]]:
        return [r for r in self.requests if r["method"] == method]


@pytest.fixture
def fake_mcp():
    fake = FakeMcp()
    with respx.mock(assert_all_called=False) as router:
        router.post(MCP_URL).mock(side_effect=fake.handler)
        yield fake
