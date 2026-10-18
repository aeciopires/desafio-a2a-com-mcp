"""Prometheus metrics for the agent (A2A side and MCP host side), with trace exemplars."""

from __future__ import annotations

from opentelemetry import trace
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram
from prometheus_client.exposition import CONTENT_TYPE_LATEST, generate_latest
from prometheus_client.openmetrics.exposition import CONTENT_TYPE_LATEST as OPENMETRICS_CONTENT_TYPE
from prometheus_client.openmetrics.exposition import generate_latest as generate_openmetrics
from starlette.requests import Request
from starlette.responses import Response

REGISTRY = CollectorRegistry()

A2A_REQUESTS = Counter("a2a_requests_total", "A2A JSON-RPC requests handled.", ["method", "outcome"], registry=REGISTRY)
A2A_REQUEST_DURATION = Histogram(
    "a2a_request_duration_seconds", "Time to answer an A2A request.", ["method"], registry=REGISTRY
)
A2A_TASKS = Counter("a2a_tasks_total", "Tasks that reached a final state.", ["final_state"], registry=REGISTRY)
A2A_TASKS_BY_STATE = Gauge(
    "a2a_tasks_by_state",
    "Tasks currently in each state (INPUT_REQUIRED = pending choices).",
    ["state"],
    registry=REGISTRY,
)
AGENT_MCP_CALLS = Counter(
    "agent_mcp_calls_total", "MCP requests sent by the agent.", ["method", "name", "result_type"], registry=REGISTRY
)
AGENT_MCP_CALL_DURATION = Histogram(
    "agent_mcp_call_duration_seconds",
    "Round-trip time of MCP requests sent by the agent.",
    ["method", "name"],
    registry=REGISTRY,
)


def exemplar() -> dict[str, str] | None:
    ctx = trace.get_current_span().get_span_context()
    return {"trace_id": format(ctx.trace_id, "032x")} if ctx.is_valid else None


async def metrics_endpoint(request: Request) -> Response:
    """Serve OpenMetrics (with exemplars) when Prometheus asks for it, plain text otherwise."""
    if "application/openmetrics-text" in request.headers.get("accept", ""):
        return Response(generate_openmetrics(REGISTRY), media_type=OPENMETRICS_CONTENT_TYPE)
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)
