"""ASGI application of the agent: Agent Card, A2A JSON-RPC endpoint and auxiliary routes."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from agent import metrics, openapi
from agent.a2a_rpc import A2AHandler
from agent.bridge import Bridge
from agent.card import build_agent_card
from agent.config import CLIENT_NAME, Settings
from agent.mcp_host import McpHost
from agent.tasks import TaskStore


def create_app(settings: Settings) -> Starlette:
    mcp = McpHost(settings.mcp_url, settings.mcp_timeout, settings.version, CLIENT_NAME)
    handler = A2AHandler(TaskStore(), Bridge(mcp))
    card = build_agent_card(settings.public_url, settings.version)
    openapi_json, docs = openapi.make_handlers(settings.version, settings.path)

    async def agent_card(_: Request) -> JSONResponse:
        return JSONResponse(card)

    async def healthz(_: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "service": settings.service_name, "version": settings.version})

    @contextlib.asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        yield
        await mcp.aclose()

    return Starlette(
        routes=[
            Route("/.well-known/agent-card.json", agent_card, methods=["GET"]),
            Route(settings.path, handler.handle, methods=["POST"]),
            Route("/healthz", healthz, methods=["GET"]),
            Route("/metrics", metrics.metrics_endpoint, methods=["GET"]),
            Route("/openapi.json", openapi_json, methods=["GET"]),
            Route("/docs", docs, methods=["GET"]),
        ],
        lifespan=lifespan,
    )
