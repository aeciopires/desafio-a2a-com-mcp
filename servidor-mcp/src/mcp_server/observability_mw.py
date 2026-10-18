"""ASGI middleware around the MCP endpoint: stderr request log, server span and metrics.

It reads the JSON-RPC body once and replays it to the SDK untouched. The W3C trace
context comes from `params._meta.traceparent`, the channel the MCP spec reserves
for it, so the span joins the caller's trace (same trace-id, new span-id).
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any

from opentelemetry.trace import SpanKind, Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mcp_server import metrics
from mcp_server.telemetry import tracer

logger = logging.getLogger("mcp_server.requests")
_propagator = TraceContextTextMapPropagator()


def _trace_ids_from_traceparent(traceparent: str | None) -> tuple[str | None, str | None]:
    parts = (traceparent or "").split("-")
    if len(parts) == 4 and len(parts[1]) == 32 and len(parts[2]) == 16:
        return parts[1], parts[2]
    return None, None


def _short_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:8]


class McpObservabilityMiddleware:
    def __init__(self, app: ASGIApp, path: str) -> None:
        self.app = app
        self.path = path.rstrip("/") or "/"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"].rstrip("/") != self.path or scope["method"] != "POST":
            await self.app(scope, receive, send)
            return

        body = await self._read_body(receive)
        request = self._parse(body)
        params = request.get("params") if isinstance(request.get("params"), dict) else {}
        meta = params.get("_meta") if isinstance(params.get("_meta"), dict) else {}
        method = str(request.get("method") or "<invalid>")
        name = params.get("name") or params.get("uri")
        traceparent = meta.get("traceparent") if isinstance(meta.get("traceparent"), str) else None
        parent = _propagator.extract({"traceparent": traceparent}) if traceparent else None

        status_holder: dict[str, Any] = {"status": 0, "chunks": []}

        async def replay() -> Message:
            nonlocal body
            if body is not None:
                chunk, body = body, None
                return {"type": "http.request", "body": chunk, "more_body": False}
            return await receive()

        async def capture(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
            elif message["type"] == "http.response.body":
                status_holder["chunks"].append(message.get("body", b""))
            await send(message)

        span_name = f"mcp {method}" + (f" {name}" if name else "")
        started = time.perf_counter()
        with tracer.start_as_current_span(span_name, context=parent, kind=SpanKind.SERVER) as span:
            span.set_attribute("rpc.system", "jsonrpc")
            span.set_attribute("mcp.method", method)
            if request.get("id") is not None:
                span.set_attribute("rpc.jsonrpc.request_id", str(request.get("id")))
            if name:
                span.set_attribute("mcp.name", str(name))
            retry_action = self._retry_action(params)
            if retry_action:
                # A string, not a bool: Grafana's Jaeger datasource (api/v3) fails on bool
                # attributes (grafana-jaeger-datasource#83).
                span.set_attribute("mcp.retry", "true")
                span.set_attribute("mrtr.action", retry_action)
                metrics.MRTR_RETRIES.labels(action=retry_action).inc()
            if isinstance(params.get("requestState"), str):
                span.set_attribute("request_state.sha256_8", _short_hash(params["requestState"]))

            await self.app(scope, replay, capture)

            elapsed = time.perf_counter() - started
            outcome = self._outcome(b"".join(status_holder["chunks"]))
            span.set_attribute("http.response.status_code", status_holder["status"])
            if outcome["result_type"]:
                span.set_attribute("mcp.result_type", outcome["result_type"])
            if outcome["is_error"]:
                span.set_attribute("mcp.is_error", "true")
            if outcome["error_code"] is not None:
                span.set_attribute("rpc.jsonrpc.error_code", outcome["error_code"])
                span.set_status(Status(StatusCode.ERROR, outcome["error_message"] or ""))

            label_name = str(name or "")
            metrics.MCP_REQUEST_DURATION.labels(method=method, name=label_name).observe(
                elapsed, exemplar=metrics.exemplar()
            )
            metrics.MCP_REQUESTS.labels(
                method=method,
                name=label_name,
                result_type=outcome["result_type"] or "error",
                outcome=outcome["label"],
            ).inc()
            if outcome["error_code"] is not None:
                metrics.MCP_PROTOCOL_ERRORS.labels(code=str(outcome["error_code"])).inc()
            if outcome["result_type"] == "input_required":
                metrics.MRTR_INPUT_REQUIRED.labels(tool=label_name).inc()

            trace_id, span_id = _trace_ids_from_traceparent(traceparent)
            ctx = span.get_span_context()
            if ctx.is_valid:
                trace_id, span_id = format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")
            logger.info(
                "%s %s",
                method,
                label_name,
                extra={
                    "method": method,
                    "id": request.get("id"),
                    "mcp_name": name,
                    "traceparent": traceparent,
                    "trace_id": trace_id,
                    "span_id": span_id,
                    "http_status": status_holder["status"],
                    "result_type": outcome["result_type"],
                    "error_code": outcome["error_code"],
                    "is_error": outcome["is_error"],
                    "mrtr_action": retry_action,
                    "duration_ms": round(elapsed * 1000, 2),
                },
            )

    @staticmethod
    async def _read_body(receive: Receive) -> bytes:
        chunks: list[bytes] = []
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                break
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break
        return b"".join(chunks)

    @staticmethod
    def _parse(body: bytes) -> dict[str, Any]:
        try:
            parsed = json.loads(body)
        except ValueError, UnicodeDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _retry_action(params: dict[str, Any]) -> str | None:
        responses = params.get("inputResponses")
        if not isinstance(responses, dict) or not responses:
            return None
        first = next(iter(responses.values()))
        return str(first.get("action")) if isinstance(first, dict) else "unknown"

    @staticmethod
    def _outcome(raw: bytes) -> dict[str, Any]:
        data: dict[str, Any] = {}
        text = raw.decode("utf-8", "replace").strip()
        if text.startswith("{"):
            try:
                data = json.loads(text)
            except ValueError:
                data = {}
        else:  # SSE framing: take the last `data:` line
            for line in text.splitlines():
                if line.startswith("data:"):
                    try:
                        data = json.loads(line[5:].strip())
                    except ValueError:
                        continue
        error = data.get("error") if isinstance(data.get("error"), dict) else None
        result = data.get("result") if isinstance(data.get("result"), dict) else {}
        is_error = bool(result.get("isError"))
        result_type = result.get("resultType") if result else None
        if error:
            label = "protocol_error"
        elif is_error:
            label = "tool_error"
        elif result_type == "input_required":
            label = "input_required"
        else:
            label = "ok"
        return {
            "result_type": result_type,
            "is_error": is_error,
            "error_code": error.get("code") if error else None,
            "error_message": error.get("message") if error else None,
            "label": label,
        }
