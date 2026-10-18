"""A2A v1.0 JSON-RPC binding: `SendMessage` and `GetTask`.

Hand-written instead of using `a2a-sdk` 1.2.2: that SDK treats a request without
the `A2A-Version` header as A2A 0.3 and rejects it with -32009, while the
challenge contract (exemplos/wire/08..10 and the validator) sends no such header.
"""

from __future__ import annotations

import json
import logging
import time
from contextvars import ContextVar
from typing import Any

from opentelemetry import trace
from opentelemetry.trace import SpanKind
from starlette.requests import Request
from starlette.responses import JSONResponse

from agent import metrics
from agent.bridge import Bridge
from agent.tasks import Task, TaskState, TaskStore
from agent.telemetry import tracer
from agent.tracing import context_from_header, current_trace_id, new_trace_id, parse_traceparent

logger = logging.getLogger("agent.a2a")

# Trace exemplar of the current request, captured while its server span is still open.
_request_exemplar: ContextVar[dict[str, str] | None] = ContextVar("request_exemplar", default=None)

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
TASK_NOT_FOUND = -32001
UNSUPPORTED_OPERATION = -32004


class RpcError(Exception):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def _error(rpc_id: Any, exc: RpcError) -> dict[str, Any]:
    error: dict[str, Any] = {"code": exc.code, "message": exc.message}
    if exc.data is not None:
        error["data"] = exc.data
    return {"jsonrpc": "2.0", "id": rpc_id, "error": error}


def _sanitize_user_message(message: dict[str, Any]) -> dict[str, Any]:
    """Keep only the A2A Message fields this agent understands (text parts)."""
    clean: dict[str, Any] = {
        "messageId": str(message.get("messageId") or ""),
        "role": "ROLE_USER",
        "parts": [{"text": str(p.get("text", ""))} for p in message.get("parts", []) if isinstance(p, dict)],
    }
    for key in ("taskId", "contextId"):
        if message.get(key):
            clean[key] = str(message[key])
    return clean


def _message_text(message: dict[str, Any]) -> str:
    return "\n".join(part["text"] for part in message["parts"] if part.get("text"))


class A2AHandler:
    def __init__(self, store: TaskStore, bridge: Bridge) -> None:
        self.store = store
        self.bridge = bridge

    async def handle(self, request: Request) -> JSONResponse:
        started = time.perf_counter()
        _request_exemplar.set(None)
        rpc_id: Any = None
        method = "<invalid>"
        try:
            try:
                payload = json.loads(await request.body())
            except ValueError as exc:
                raise RpcError(PARSE_ERROR, "Parse error: body is not valid JSON") from exc
            if (
                not isinstance(payload, dict)
                or payload.get("jsonrpc") != "2.0"
                or not isinstance(payload.get("method"), str)
            ):
                raise RpcError(INVALID_REQUEST, "Invalid Request: expected a JSON-RPC 2.0 object with a method")
            rpc_id = payload.get("id")
            method = payload["method"]
            params = payload.get("params")
            if not isinstance(params, dict):
                raise RpcError(INVALID_PARAMS, "params must be an object")
            header = request.headers.get("traceparent")
            if method == "SendMessage":
                result = await self.send_message(params, header)
            elif method == "GetTask":
                result = self.get_task(params)
            else:
                raise RpcError(METHOD_NOT_FOUND, f"Method not found: {method}. Supported: SendMessage, GetTask")
            response = {"jsonrpc": "2.0", "id": rpc_id, "result": result}
            outcome = "ok"
        except RpcError as exc:
            response = _error(rpc_id, exc)
            outcome = f"error_{exc.code}"
            logger.warning(
                "A2A %s rejected: %s",
                method,
                exc.message,
                extra={"event": "a2a_error", "a2a_method": method, "error_code": exc.code},
            )
        except Exception:  # noqa: BLE001 - always answer JSON-RPC, never a bare 500
            logger.exception("A2A %s failed", method, extra={"event": "a2a_internal_error", "a2a_method": method})
            response = _error(rpc_id, RpcError(INTERNAL_ERROR, "Internal error"))
            outcome = "error_internal"
        metrics.A2A_REQUEST_DURATION.labels(method=method).observe(
            time.perf_counter() - started, exemplar=_request_exemplar.get()
        )
        metrics.A2A_REQUESTS.labels(method=method, outcome=outcome).inc()
        return JSONResponse(response)

    async def send_message(self, params: dict[str, Any], traceparent: str | None) -> dict[str, Any]:
        message = params.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("parts"), list) or not message["parts"]:
            raise RpcError(INVALID_PARAMS, "params.message with at least one part is required")
        user_message = _sanitize_user_message(message)
        task_id = user_message.get("taskId")

        if task_id:
            task = self.store.get(task_id)
            if task is None:
                raise RpcError(TASK_NOT_FOUND, f"Task not found: {task_id}")
        else:
            task = self.store.create(user_message.get("contextId"))

        parent = context_from_header(traceparent) or task.trace_context
        with tracer.start_as_current_span("a2a SendMessage", context=parent, kind=SpanKind.SERVER) as span:
            async with task.lock:
                self._bind_trace(task, traceparent, span)
                span.set_attribute("a2a.method", "SendMessage")
                span.set_attribute("a2a.task_id", task.id)
                span.set_attribute("a2a.context_id", task.context_id)
                if task_id:
                    await self._continue(task, user_message)
                else:
                    task.add_user_message(user_message)
                    await self.bridge.start(task, _message_text(user_message))
                span.set_attribute("a2a.task_state", task.state.value)
                _request_exemplar.set(metrics.exemplar())
                return {"task": task.to_wire()}

    async def _continue(self, task: Task, user_message: dict[str, Any]) -> None:
        if task.is_terminal:
            raise RpcError(
                UNSUPPORTED_OPERATION,
                f"Task {task.id} is in terminal state {task.state.value} and cannot accept new messages",
                {"taskId": task.id, "state": task.state.value},
            )
        if task.state is not TaskState.INPUT_REQUIRED:
            raise RpcError(
                UNSUPPORTED_OPERATION,
                f"Task {task.id} is {task.state.value}; only TASK_STATE_INPUT_REQUIRED accepts a follow-up",
            )
        task.add_user_message(user_message)
        await self.bridge.resume(task, _message_text(user_message))

    @staticmethod
    def _bind_trace(task: Task, traceparent: str | None, span: trace.Span) -> None:
        """Keep the client's trace-id for every MCP request of this Task, across the pause."""
        parsed = parse_traceparent(traceparent)
        if parsed:
            task.trace_id = parsed[0]
        span_ctx = span.get_span_context()
        if task.trace_id is None:
            task.trace_id = format(span_ctx.trace_id, "032x") if span_ctx.is_valid else new_trace_id()
        if task.trace_context is None and span_ctx.is_valid:
            task.trace_context = trace.set_span_in_context(span)
        current_trace_id.set(task.trace_id)

    def get_task(self, params: dict[str, Any]) -> dict[str, Any]:
        task_id = params.get("id")
        if not isinstance(task_id, str) or not task_id:
            raise RpcError(INVALID_PARAMS, "params.id (the task id) is required")
        task = self.store.get(task_id)
        if task is None:
            raise RpcError(TASK_NOT_FOUND, f"Task not found: {task_id}")
        with tracer.start_as_current_span("a2a GetTask", context=task.trace_context, kind=SpanKind.SERVER) as span:
            span.set_attribute("a2a.method", "GetTask")
            span.set_attribute("a2a.task_id", task.id)
            span.set_attribute("a2a.task_state", task.state.value)
            _request_exemplar.set(metrics.exemplar())
            return {"task": task.to_wire()}
