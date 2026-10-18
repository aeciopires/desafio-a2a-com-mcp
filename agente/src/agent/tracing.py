"""W3C trace context for the bridge: from the A2A `traceparent` header to the MCP `_meta`.

The trace-id the A2A client sent is kept for every MCP request of the Task; the
span-id is new for each request. With OpenTelemetry on, the ids come from real
spans; with it off (`OTEL_SDK_DISABLED=true`) they are built by hand, so the
propagation never depends on a collector being around.
"""

from __future__ import annotations

import re
import secrets
from contextvars import ContextVar

from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

_TRACEPARENT = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$")
_propagator = TraceContextTextMapPropagator()

# Trace-id of the Task being processed, used when no recording span is active.
current_trace_id: ContextVar[str | None] = ContextVar("current_trace_id", default=None)


def parse_traceparent(header: str | None) -> tuple[str, str] | None:
    """Return (trace_id, span_id) of a valid version-00 traceparent, else None."""
    if not header:
        return None
    match = _TRACEPARENT.match(header.strip().lower())
    if not match or set(match.group(1)) == {"0"} or set(match.group(2)) == {"0"}:
        return None
    return match.group(1), match.group(2)


def context_from_header(header: str | None) -> otel_context.Context | None:
    """OpenTelemetry parent context extracted from an incoming `traceparent`, if valid."""
    if parse_traceparent(header) is None:
        return None
    return _propagator.extract({"traceparent": header.strip().lower()})  # type: ignore[union-attr]


def new_trace_id() -> str:
    return secrets.token_hex(16)


def outbound_traceparent() -> str:
    """`traceparent` for the next MCP request: current span if recording, else hand-built."""
    span_ctx = trace.get_current_span().get_span_context()
    if span_ctx.is_valid:
        return f"00-{span_ctx.trace_id:032x}-{span_ctx.span_id:016x}-{int(span_ctx.trace_flags):02x}"
    trace_id = current_trace_id.get() or new_trace_id()
    return f"00-{trace_id}-{secrets.token_hex(8)}-01"
