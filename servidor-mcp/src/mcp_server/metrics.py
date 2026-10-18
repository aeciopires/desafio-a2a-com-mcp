"""Prometheus metrics for the MCP server (protocol and business), with trace exemplars."""

from __future__ import annotations

import logging

from opentelemetry import trace
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram
from prometheus_client.exposition import CONTENT_TYPE_LATEST, generate_latest
from prometheus_client.openmetrics.exposition import CONTENT_TYPE_LATEST as OPENMETRICS_CONTENT_TYPE
from prometheus_client.openmetrics.exposition import generate_latest as generate_openmetrics
from starlette.requests import Request
from starlette.responses import Response

REGISTRY = CollectorRegistry()

MCP_REQUESTS = Counter(
    "mcp_requests_total",
    "MCP JSON-RPC requests handled.",
    ["method", "name", "result_type", "outcome"],
    registry=REGISTRY,
)
MCP_REQUEST_DURATION = Histogram(
    "mcp_request_duration_seconds",
    "Time to answer an MCP request.",
    ["method", "name"],
    registry=REGISTRY,
)
MCP_PROTOCOL_ERRORS = Counter(
    "mcp_protocol_errors_total", "JSON-RPC errors returned, by code.", ["code"], registry=REGISTRY
)
MCP_TOOL_ERRORS = Counter(
    "mcp_tool_errors_total", "Tool execution errors (isError), by rule.", ["tool", "reason"], registry=REGISTRY
)
RESERVATIONS_CREATED = Counter(
    "reservations_created_total",
    "Reservations created at runtime.",
    ["room", "responsible", "date"],
    registry=REGISTRY,
)
RESERVATIONS_ACTIVE = Gauge(
    "reservations_active", "Reservations currently held in memory, by room.", ["room"], registry=REGISTRY
)
MRTR_INPUT_REQUIRED = Counter(
    "mrtr_input_required_total", "input_required results returned (room conflicts).", ["tool"], registry=REGISTRY
)
MRTR_RETRIES = Counter(
    "mrtr_retries_total", "MRTR retries received, by elicitation action.", ["action"], registry=REGISTRY
)
REQUEST_STATE_REJECTED = Counter(
    "request_state_rejected_total", "requestState values rejected, by reason.", ["reason"], registry=REGISTRY
)


def exemplar() -> dict[str, str] | None:
    ctx = trace.get_current_span().get_span_context()
    return {"trace_id": format(ctx.trace_id, "032x")} if ctx.is_valid else None


async def metrics_endpoint(request: Request) -> Response:
    """Serve OpenMetrics (with exemplars) when Prometheus asks for it, plain text otherwise."""
    if "application/openmetrics-text" in request.headers.get("accept", ""):
        return Response(generate_openmetrics(REGISTRY), media_type=OPENMETRICS_CONTENT_TYPE)
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)


_REJECTION_REASONS = {
    "expired": "expired",
    "request binding": "mismatch",
    "audience": "mismatch",
    "seal": "tampered",
    "malformed": "tampered",
    "unknown key": "tampered",
    "non-string requestState": "tampered",
}


class RequestStateRejectionCounter(logging.Handler):
    """Counts the SDK's requestState rejections by reason.

    The SDK answers every rejection with the same frozen -32602 on the wire and
    logs the real reason (`requestState rejected on <method>: <reason>`) on its
    own logger, which is where this handler listens.
    """

    def emit(self, record: logging.LogRecord) -> None:
        if not record.msg.startswith("requestState rejected") or len(record.args or ()) < 2:
            return
        reason = str(record.args[1])  # type: ignore[index]
        REQUEST_STATE_REJECTED.labels(reason=_REJECTION_REASONS.get(reason, "other")).inc()
