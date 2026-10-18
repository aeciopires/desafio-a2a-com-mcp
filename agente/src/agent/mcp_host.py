"""The agent's MCP client: stateless, one JSON-RPC request per HTTP POST.

Why not the SDK's `Client`: it resolves `input_required` itself through an
elicitation callback (the Task would never pause), and when a callback is set it
declares `elicitation: {form, url}`, while this agent must declare exactly
`{"elicitation": {"form": {}}}`. So the transport is a thin httpx client, and the
results are typed with the SDK's own `mcp_types` models.

Every request carries the full `_meta` (no session, nothing inferred from earlier
requests), the headers the transport mirrors from the body, and a fresh JSON-RPC
id, so a retry never reuses the id of the request it retries.
"""

from __future__ import annotations

import itertools
import json
import logging
import time
from typing import Any

import httpx
import mcp_types
from opentelemetry.trace import SpanKind, Status, StatusCode

from agent import metrics
from agent.telemetry import tracer
from agent.tracing import outbound_traceparent

PROTOCOL_VERSION = "2026-07-28"
CLIENT_CAPABILITIES: dict[str, Any] = {"elicitation": {"form": {}}}

logger = logging.getLogger("agent.mcp")

ToolResult = mcp_types.CallToolResult | mcp_types.InputRequiredResult


class McpRpcError(Exception):
    """The MCP server answered with a JSON-RPC error."""

    def __init__(self, code: int, message: str, data: Any = None, http_status: int | None = None) -> None:
        super().__init__(f"MCP error {code}: {message}")
        self.code = code
        self.message = message
        self.data = data
        self.http_status = http_status


class McpUnavailable(Exception):
    """The MCP server could not be reached or answered something that is not JSON-RPC."""


class McpHost:
    def __init__(self, url: str, timeout: float, client_version: str, client_name: str) -> None:
        self.url = url
        self._client = httpx.AsyncClient(timeout=timeout)
        self._ids = itertools.count(1)
        self._client_info = {"name": client_name, "version": client_version}

    async def aclose(self) -> None:
        await self._client.aclose()

    def next_id(self) -> int:
        return next(self._ids)

    async def request(self, method: str, params: dict[str, Any], name: str | None = None) -> dict[str, Any]:
        request_id = self.next_id()
        span_name = f"mcp {method}" + (f" {name}" if name else "")
        with tracer.start_as_current_span(span_name, kind=SpanKind.CLIENT) as span:
            traceparent = outbound_traceparent()
            body = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": {
                    **params,
                    "_meta": {
                        mcp_types.PROTOCOL_VERSION_META_KEY: PROTOCOL_VERSION,
                        mcp_types.CLIENT_INFO_META_KEY: self._client_info,
                        mcp_types.CLIENT_CAPABILITIES_META_KEY: CLIENT_CAPABILITIES,
                        "traceparent": traceparent,
                    },
                },
            }
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": PROTOCOL_VERSION,
                "Mcp-Method": method,
            }
            if name:
                headers["Mcp-Name"] = name
            span.set_attribute("rpc.system", "jsonrpc")
            span.set_attribute("rpc.jsonrpc.request_id", str(request_id))
            span.set_attribute("mcp.method", method)
            # A string, not a bool: Grafana's Jaeger datasource (api/v3) fails on bool
            # attributes (grafana-jaeger-datasource#83).
            span.set_attribute("mcp.retry", str("requestState" in params).lower())
            if name:
                span.set_attribute("mcp.name", name)

            started = time.perf_counter()
            result_type = "error"
            try:
                response = await self._client.post(self.url, json=body, headers=headers)
            except httpx.HTTPError as exc:
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                logger.error(
                    "MCP server unreachable at %s: %s",
                    self.url,
                    exc,
                    extra={"event": "mcp_unreachable", "mcp_method": method, "mcp_request_id": request_id},
                )
                raise McpUnavailable(f"MCP server unreachable at {self.url}: {exc}") from exc
            finally:
                elapsed = time.perf_counter() - started
                metrics.AGENT_MCP_CALL_DURATION.labels(method=method, name=name or "").observe(
                    elapsed, exemplar=metrics.exemplar()
                )

            try:
                payload = self._decode(response)
                if "error" in payload:
                    error = payload["error"] or {}
                    span.set_attribute("rpc.jsonrpc.error_code", error.get("code", 0))
                    span.set_status(Status(StatusCode.ERROR, str(error.get("message"))))
                    raise McpRpcError(
                        int(error.get("code", 0)),
                        str(error.get("message", "")),
                        error.get("data"),
                        response.status_code,
                    )
                result = payload.get("result")
                if not isinstance(result, dict):
                    raise McpUnavailable(f"MCP server at {self.url} answered without a result: {payload!r:.200}")
                result_type = str(result.get("resultType", "complete"))
                span.set_attribute("mcp.result_type", result_type)
                if result.get("isError"):
                    span.set_attribute("mcp.is_error", "true")
                return result
            finally:
                metrics.AGENT_MCP_CALLS.labels(method=method, name=name or "", result_type=result_type).inc()
                logger.info(
                    "MCP %s %s -> %s",
                    method,
                    name or "",
                    result_type,
                    extra={
                        "event": "mcp_call",
                        "mcp_method": method,
                        "mcp_name": name,
                        "mcp_request_id": request_id,
                        "mcp_result_type": result_type,
                        "http_status": response.status_code,
                        "duration_ms": round(elapsed * 1000, 2),
                    },
                )

    def _decode(self, response: httpx.Response) -> dict[str, Any]:
        content_type = response.headers.get("content-type", "")
        text = response.text
        if "text/event-stream" in content_type:
            data_lines = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
            text = data_lines[-1] if data_lines else ""
        try:
            payload = json.loads(text)
        except ValueError as exc:
            raise McpUnavailable(
                f"MCP server at {self.url} answered HTTP {response.status_code} with non-JSON body: {text[:200]!r}"
            ) from exc
        if not isinstance(payload, dict):
            raise McpUnavailable(f"MCP server at {self.url} answered a non-object JSON-RPC payload")
        return payload

    async def list_tools(self) -> list[mcp_types.Tool]:
        result = await self.request("tools/list", {})
        return mcp_types.ListToolsResult.model_validate(result).tools

    async def read_text_resource(self, uri: str) -> str:
        result = mcp_types.ReadResourceResult.model_validate(await self.request("resources/read", {"uri": uri}, uri))
        texts = [c.text for c in result.contents if isinstance(c, mcp_types.TextResourceContents)]
        if not texts:
            raise McpUnavailable(f"resource {uri} has no text content")
        return texts[0]

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        input_responses: dict[str, Any] | None = None,
        request_state: str | None = None,
    ) -> ToolResult:
        params: dict[str, Any] = {"name": name, "arguments": arguments}
        if input_responses is not None:
            params["inputResponses"] = input_responses
        if request_state is not None:
            # Echoed byte for byte: the agent never opens, parses or rebuilds it.
            params["requestState"] = request_state
        result = await self.request("tools/call", params, name)
        if result.get("resultType") == "input_required":
            return mcp_types.InputRequiredResult.model_validate(result)
        return mcp_types.CallToolResult.model_validate(result)
