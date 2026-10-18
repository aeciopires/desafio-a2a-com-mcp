"""THE BRIDGE: where MCP's `input_required` meets A2A's `TASK_STATE_INPUT_REQUIRED`.

Neither protocol has a session. MCP carries its state in `requestState`, which
the client must echo on a retry; A2A carries it in the Task. This module joins
the two:

1. `start()` calls `tools/call reservar_sala`. When the MCP server answers
   `input_required`, `_pause()` puts the Task in `TASK_STATE_INPUT_REQUIRED`
   with the line `alternativas: ...` and stores the `requestState` (plus the
   `inputRequests` key and the original arguments) on that Task only.
2. `resume()` handles the follow-up `SendMessage` (`escolha=...`): it repeats the
   original `tools/call` with a NEW JSON-RPC id, the same arguments,
   `inputResponses` under the same key, and the `requestState` echoed unchanged.

The agent never opens the `requestState` and never applies room rules: conflicts,
policy and alternatives are decided by the MCP server.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import mcp_types
from opentelemetry import trace

from agent.mcp_host import McpHost, McpRpcError, McpUnavailable, ToolResult
from agent.parser import DECLINE, ParseError, parse_booking, parse_choice
from agent.tasks import PendingInput, Task, TaskState
from agent.telemetry import tracer

logger = logging.getLogger("agent.bridge")

BOOKING_TOOL = "reservar_sala"
POLICY_URI = "politica://uso"
ALTERNATIVES_PREFIX = "alternativas: "


class BridgeError(Exception):
    """Something the bridge cannot translate; the Task fails with this message."""


def alternatives_line(allowed: list[str]) -> str:
    return ALTERNATIVES_PREFIX + ", ".join(allowed)


def extract_policy_version(text: str) -> str:
    """The policy resource declares its version on the first line: `versao: <value>`."""
    first = text.strip().splitlines()[0] if text.strip() else ""
    key, _, value = first.partition(":")
    if key.strip().lower() != "versao" or not value.strip():
        raise BridgeError(f"O resource {POLICY_URI} nao declara a versao na primeira linha")
    return value.strip()


def allowed_choices(schema: dict[str, Any]) -> list[str]:
    """Options offered by a flat form schema: `enum`, or `const` when there is a single one."""
    prop = (schema.get("properties") or {}).get("sala") or {}
    if isinstance(prop.get("enum"), list):
        return [str(v) for v in prop["enum"]]
    if "const" in prop:
        return [str(prop["const"])]
    raise BridgeError("A elicitation recebida do servidor MCP nao restringe a propriedade 'sala'")


def tool_error_text(result: mcp_types.CallToolResult) -> str:
    texts = [c.text for c in result.content if isinstance(c, mcp_types.TextContent)]
    return " ".join(texts) or "A tool devolveu erro sem mensagem"


class Bridge:
    def __init__(self, mcp: McpHost) -> None:
        self.mcp = mcp

    async def start(self, task: Task, text: str) -> None:
        """First message of a Task: discover, read the policy, call the booking tool."""
        task.transition(TaskState.WORKING)
        try:
            request = parse_booking(text)
            await self._discover(task)
            result = await self.mcp.call_tool(BOOKING_TOOL, request.as_arguments())
            self._apply(task, BOOKING_TOOL, request.as_arguments(), result)
        except ParseError as exc:
            task.transition(TaskState.FAILED, str(exc))
        except (McpRpcError, McpUnavailable, BridgeError) as exc:
            task.transition(TaskState.FAILED, self._describe(exc))

    async def resume(self, task: Task, text: str) -> None:
        """Follow-up message on a paused Task: translate `escolha=` into the MCP retry."""
        pending = task.pending
        if pending is None:  # defensive: only INPUT_REQUIRED Tasks get here
            task.transition(TaskState.FAILED, "Task sem pergunta pendente")
            return

        choice = parse_choice(text)
        if choice is None or (choice != DECLINE and choice not in pending.allowed):
            # Not an option the server offered: stay paused and repeat the same question.
            task.repeat_status()
            logger.info(
                "invalid choice %r for task %s; still waiting",
                text,
                task.id,
                extra={"event": "invalid_choice", "task_id": task.id, "task_state": task.state.value},
            )
            return

        if choice == DECLINE:
            response: dict[str, Any] = mcp_types.ElicitResult(action="decline").model_dump(
                by_alias=True, exclude_none=True, mode="json"
            )
        else:
            response = mcp_types.ElicitResult(action="accept", content={"sala": choice}).model_dump(
                by_alias=True, exclude_none=True, mode="json"
            )

        task.transition(TaskState.WORKING)
        task.pending = None
        with tracer.start_as_current_span("bridge.resume") as span:
            span.set_attribute("a2a.task_id", task.id)
            span.set_attribute("mrtr.action", response["action"])
            try:
                result = await self.mcp.call_tool(
                    pending.tool,
                    pending.arguments,
                    input_responses={pending.input_key: response},
                    request_state=pending.request_state,
                )
                self._apply(task, pending.tool, pending.arguments, result)
            except (McpRpcError, McpUnavailable, BridgeError) as exc:
                task.transition(TaskState.FAILED, self._describe(exc))

    async def _discover(self, task: Task) -> None:
        """Runtime discovery (`tools/list`) and the policy version (`resources/read`)."""
        tools = await self.mcp.list_tools()
        if BOOKING_TOOL not in {tool.name for tool in tools}:
            raise BridgeError(f"O servidor MCP nao oferece a tool {BOOKING_TOOL}")
        task.policy_version = extract_policy_version(await self.mcp.read_text_resource(POLICY_URI))

    def _apply(self, task: Task, tool: str, arguments: dict[str, Any], result: ToolResult) -> None:
        if isinstance(result, mcp_types.InputRequiredResult):
            self._pause(task, tool, arguments, result)
            return
        if result.is_error:
            task.transition(TaskState.FAILED, tool_error_text(result))
            return
        data = result.structured_content or {}
        if not data.get("reservado"):
            task.transition(TaskState.CANCELED, "Reserva nao realizada: as alternativas foram recusadas.")
            return
        reservation = {
            "reserva": data.get("reserva"),
            "sala": data.get("sala"),
            "inicio": data.get("inicio"),
            "fim": data.get("fim"),
            "responsavel": data.get("responsavel"),
            "politica": task.policy_version,
        }
        task.add_artifact("reserva", json.dumps(reservation, ensure_ascii=False))
        task.transition(TaskState.COMPLETED, f"Reserva {reservation['reserva']} confirmada na {reservation['sala']}.")

    def _pause(self, task: Task, tool: str, arguments: dict[str, Any], result: mcp_types.InputRequiredResult) -> None:
        """MCP `input_required` -> A2A `TASK_STATE_INPUT_REQUIRED`, with the state kept on this Task."""
        requests = result.input_requests or {}
        if len(requests) != 1 or not result.request_state:
            raise BridgeError("input_required sem exatamente um inputRequest e um requestState")
        input_key, input_request = next(iter(requests.items()))
        if not isinstance(input_request, mcp_types.ElicitRequest):
            raise BridgeError(f"inputRequest {input_key!r} nao e uma elicitation")
        params = input_request.params
        if getattr(params, "mode", "form") != "form":
            raise BridgeError("A elicitation recebida nao esta em form mode")
        allowed = allowed_choices(params.requested_schema)  # type: ignore[union-attr]

        with tracer.start_as_current_span("bridge.pause") as span:
            span.set_attribute("a2a.task_id", task.id)
            span.set_attribute("mrtr.alternatives_count", len(allowed))
            task.pending = PendingInput(
                tool=tool,
                arguments=dict(arguments),
                input_key=input_key,
                request_state=result.request_state,
                allowed=allowed,
            )
            task.transition(TaskState.INPUT_REQUIRED, alternatives_line(allowed))
        trace.get_current_span().set_attribute("a2a.task_state", task.state.value)

    @staticmethod
    def _describe(exc: Exception) -> str:
        if isinstance(exc, McpRpcError):
            return f"Erro do servidor MCP ({exc.code}): {exc.message}"
        return str(exc)
