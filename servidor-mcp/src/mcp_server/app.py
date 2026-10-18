"""ASGI application: the SDK's Streamable HTTP endpoint plus auxiliary routes."""

from __future__ import annotations

import logging

from starlette.requests import Request
from starlette.responses import JSONResponse

from mcp_server import metrics, openapi
from mcp_server.config import Settings
from mcp_server.observability_mw import McpObservabilityMiddleware
from mcp_server.repository import Repository
from mcp_server.server import build_server
from mcp_server.service import BookingService


def create_app(settings: Settings) -> McpObservabilityMiddleware:
    """Build the app. The wrapped Starlette app is available as `.app` (tests use its lifespan)."""
    service = BookingService(Repository.from_data_dir(settings.data_dir))
    server = build_server(settings, service)
    logging.getLogger("mcp.server.request_state").addHandler(metrics.RequestStateRejectionCounter())

    openapi_json, docs = openapi.make_handlers(settings.version, settings.path)

    @server.custom_route("/healthz", methods=["GET"], include_in_schema=False)
    async def healthz(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "service": settings.service_name, "version": settings.version})

    server.custom_route("/metrics", methods=["GET"], include_in_schema=False)(metrics.metrics_endpoint)
    server.custom_route("/openapi.json", methods=["GET"], include_in_schema=False)(openapi_json)
    server.custom_route("/docs", methods=["GET"], include_in_schema=False)(docs)

    app = server.streamable_http_app(
        streamable_http_path=settings.path,
        stateless_http=True,
        json_response=True,
        # 127.0.0.1/localhost turn on the SDK's DNS-rebinding protection; 0.0.0.0 (containers) does not.
        host=settings.host,
    )
    return McpObservabilityMiddleware(app, settings.path)
