"""Hand-written OpenAPI 3.1 document and Swagger UI for manual testing of the MCP endpoint.

These routes live beside `/mcp` but never pass through the MCP `_meta` validation.
"""

from __future__ import annotations

from typing import Any

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse

SWAGGER_UI_VERSION = "5.33.3"
PROTOCOL_VERSION = "2026-07-28"

_META = {
    "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
    "io.modelcontextprotocol/clientInfo": {"name": "swagger-ui", "version": "1.0.0"},
    "io.modelcontextprotocol/clientCapabilities": {"elicitation": {"form": {}}},
    "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
}

_RESERVA_CONFLITO = {
    "sala": "sala-garagem",
    "inicio": "2026-11-03T14:00:00-03:00",
    "fim": "2026-11-03T15:00:00-03:00",
    "responsavel": "Marty",
}


def _rpc(rpc_id: int, method: str, params: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": {**params, "_meta": _META}}


_EXAMPLES: dict[str, dict[str, Any]] = {
    "tools-list": {
        "summary": "tools/list (Mcp-Method: tools/list)",
        "value": _rpc(1, "tools/list", {}),
    },
    "listar-salas": {
        "summary": "tools/call listar_salas (Mcp-Name: listar_salas)",
        "value": _rpc(2, "tools/call", {"name": "listar_salas", "arguments": {}}),
    },
    "consultar-disponibilidade": {
        "summary": "tools/call consultar_disponibilidade",
        "value": _rpc(
            3,
            "tools/call",
            {
                "name": "consultar_disponibilidade",
                "arguments": {k: v for k, v in _RESERVA_CONFLITO.items() if k != "responsavel"},
            },
        ),
    },
    "reservar-livre": {
        "summary": "tools/call reservar_sala, sala livre -> complete",
        "value": _rpc(
            4,
            "tools/call",
            {
                "name": "reservar_sala",
                "arguments": {
                    "sala": "sala-aquario",
                    "inicio": "2026-11-03T09:00:00-03:00",
                    "fim": "2026-11-03T10:00:00-03:00",
                    "responsavel": "Doc",
                },
            },
        ),
    },
    "reservar-conflito": {
        "summary": "tools/call reservar_sala, sala ocupada -> input_required",
        "value": _rpc(5, "tools/call", {"name": "reservar_sala", "arguments": _RESERVA_CONFLITO}),
    },
    "reservar-retry": {
        "summary": "Retry com id novo: cole a chave do inputRequests e o requestState recebidos",
        "value": _rpc(
            6,
            "tools/call",
            {
                "name": "reservar_sala",
                "arguments": _RESERVA_CONFLITO,
                "inputResponses": {"<chave do inputRequests>": {"action": "accept", "content": {"sala": "sala-fusca"}}},
                "requestState": "<requestState recebido>",
            },
        ),
    },
    "reservar-recusa": {
        "summary": "Retry com action decline -> complete, reservado=false",
        "value": _rpc(
            7,
            "tools/call",
            {
                "name": "reservar_sala",
                "arguments": _RESERVA_CONFLITO,
                "inputResponses": {"<chave do inputRequests>": {"action": "decline"}},
                "requestState": "<requestState recebido>",
            },
        ),
    },
    "sem-elicitation": {
        "summary": "Conflito sem a capability de elicitation -> -32021 / HTTP 400",
        "value": {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {
                "name": "reservar_sala",
                "arguments": _RESERVA_CONFLITO,
                "_meta": {**_META, "io.modelcontextprotocol/clientCapabilities": {}},
            },
        },
    },
    "politica": {
        "summary": "resources/read politica://uso (Mcp-Name: politica://uso)",
        "value": _rpc(9, "resources/read", {"uri": "politica://uso"}),
    },
}


def build_openapi(version: str, mcp_path: str) -> dict[str, Any]:
    header = lambda name, desc, example: {  # noqa: E731
        "name": name,
        "in": "header",
        "required": name != "Mcp-Name",
        "description": desc,
        "schema": {"type": "string", "example": example},
    }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Central de Salas - servidor MCP",
            "version": version,
            "description": (
                "Endpoint MCP Streamable HTTP (stateless, revisao 2026-07-28). Cada request carrega "
                "`_meta` completo; os headers `Mcp-Method`/`Mcp-Name` precisam espelhar o corpo "
                "(divergencia -> -32020). Escolha um exemplo, ajuste os headers e execute."
            ),
        },
        "paths": {
            mcp_path: {
                "post": {
                    "summary": "JSON-RPC MCP (tools/list, tools/call, resources/read)",
                    "parameters": [
                        header("MCP-Protocol-Version", "Versao do protocolo MCP", PROTOCOL_VERSION),
                        header("Mcp-Method", "Espelha `method` do corpo", "tools/call"),
                        header(
                            "Mcp-Name", "Nome da tool ou URI do resource (tools/call, resources/read)", "reservar_sala"
                        ),
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"type": "object"}, "examples": _EXAMPLES}},
                    },
                    "responses": {
                        "200": {"description": "Resultado JSON-RPC (complete ou input_required)"},
                        "400": {"description": "Erro de protocolo (-32602, -32021, -32020)"},
                    },
                }
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


def make_handlers(version: str, mcp_path: str):
    document = build_openapi(version, mcp_path)

    async def openapi_json(_: Request) -> JSONResponse:
        return JSONResponse(document)

    async def docs(_: Request) -> HTMLResponse:
        return HTMLResponse(swagger_html("Central de Salas - MCP"))

    return openapi_json, docs
