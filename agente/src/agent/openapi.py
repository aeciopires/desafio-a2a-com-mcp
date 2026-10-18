"""Hand-written OpenAPI 3.1 document and Swagger UI for manual testing of the A2A endpoint."""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

SWAGGER_UI_VERSION = "5.33.3"


def _send(rpc_id: int, text: str, task_id: str | None = None) -> dict[str, Any]:
    message: dict[str, Any] = {"messageId": f"msg-swagger-{rpc_id}", "role": "ROLE_USER", "parts": [{"text": text}]}
    if task_id:
        message["taskId"] = task_id
    return {"jsonrpc": "2.0", "id": rpc_id, "method": "SendMessage", "params": {"message": message}}


_EXAMPLES: dict[str, dict[str, Any]] = {
    "sala-livre": {
        "summary": "SendMessage: sala livre -> TASK_STATE_COMPLETED",
        "value": _send(
            1, "reservar sala=sala-porao inicio=2026-11-03T09:00:00-03:00 fim=2026-11-03T10:00:00-03:00 responsavel=Doc"
        ),
    },
    "sala-ocupada": {
        "summary": "SendMessage: sala ocupada -> TASK_STATE_INPUT_REQUIRED",
        "value": _send(
            2,
            "reservar sala=sala-garagem inicio=2026-11-03T14:00:00-03:00 fim=2026-11-03T15:00:00-03:00 "
            "responsavel=Marty",
        ),
    },
    "escolha": {
        "summary": "Continuacao: escolha=<id> (troque o taskId)",
        "value": _send(3, "escolha=sala-mirante", "<taskId devolvido na pausa>"),
    },
    "recusa": {
        "summary": "Continuacao: escolha=recusar -> TASK_STATE_CANCELED",
        "value": _send(4, "escolha=recusar", "<taskId devolvido na pausa>"),
    },
    "sala-inexistente": {
        "summary": "SendMessage: sala inexistente -> TASK_STATE_FAILED",
        "value": _send(
            5,
            "reservar sala=sala-inexistente inicio=2026-11-03T09:00:00-03:00 fim=2026-11-03T10:00:00-03:00 "
            "responsavel=Doc",
        ),
    },
    "get-task": {
        "summary": "GetTask (troque o id)",
        "value": {"jsonrpc": "2.0", "id": 6, "method": "GetTask", "params": {"id": "<taskId>"}},
    },
}


def build_openapi(version: str, a2a_path: str) -> dict[str, Any]:
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Central de Salas - agente A2A",
            "version": version,
            "description": (
                "Binding JSON-RPC 2.0 do A2A v1.0. Envie `SendMessage` para abrir uma Task; se ela parar em "
                "`TASK_STATE_INPUT_REQUIRED`, responda com outro `SendMessage` levando o `taskId`. O header "
                "`traceparent` e opcional e e propagado ate o servidor MCP."
            ),
        },
        "paths": {
            a2a_path: {
                "post": {
                    "summary": "JSON-RPC A2A (SendMessage, GetTask)",
                    "parameters": [
                        {
                            "name": "traceparent",
                            "in": "header",
                            "required": False,
                            "description": "W3C trace context; o trace-id chega ao _meta das chamadas MCP",
                            "schema": {
                                "type": "string",
                                "example": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
                            },
                        }
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"type": "object"}, "examples": _EXAMPLES}},
                    },
                    "responses": {"200": {"description": "Resposta JSON-RPC (result.task ou error)"}},
                }
            },
            "/.well-known/agent-card.json": {
                "get": {"summary": "Agent Card (A2A v1.0)", "responses": {"200": {"description": "Agent Card"}}}
            },
            "/healthz": {"get": {"summary": "Liveness", "responses": {"200": {"description": "ok"}}}},
            "/metrics": {"get": {"summary": "Metricas Prometheus", "responses": {"200": {"description": "ok"}}}},
        },
    }


def swagger_html(title: str) -> str:
    base = f"https://cdn.jsdelivr.net/npm/swagger-ui-dist@{SWAGGER_UI_VERSION}"
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <link rel="stylesheet" href="{base}/swagger-ui.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="{base}/swagger-ui-bundle.js"></script>
  <script>
    window.ui = SwaggerUIBundle({{ url: "openapi.json", dom_id: "#swagger-ui", tryItOutEnabled: true }});
  </script>
</body>
</html>"""


def make_handlers(version: str, a2a_path: str):
    document = build_openapi(version, a2a_path)

    async def openapi_json(_: Request) -> JSONResponse:
        return JSONResponse(document)

    async def docs(_: Request) -> HTMLResponse:
        return HTMLResponse(swagger_html("Central de Salas - agente A2A"))

    return openapi_json, docs
