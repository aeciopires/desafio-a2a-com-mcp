"""A2A Task: identity, state machine and product, held in memory.

Serialization goes through an allowlist (`to_wire`), so the MCP state kept on the
Task for the bridge (`pending`) can never leak into an A2A response.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from opentelemetry import context as otel_context

from agent import metrics

logger = logging.getLogger("agent.tasks")


class TaskState(StrEnum):
    SUBMITTED = "TASK_STATE_SUBMITTED"
    WORKING = "TASK_STATE_WORKING"
    INPUT_REQUIRED = "TASK_STATE_INPUT_REQUIRED"
    COMPLETED = "TASK_STATE_COMPLETED"
    FAILED = "TASK_STATE_FAILED"
    CANCELED = "TASK_STATE_CANCELED"


TERMINAL_STATES = frozenset({TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED})

_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.SUBMITTED: frozenset({TaskState.WORKING, TaskState.FAILED, TaskState.CANCELED}),
    TaskState.WORKING: frozenset({TaskState.INPUT_REQUIRED, TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED}),
    TaskState.INPUT_REQUIRED: frozenset({TaskState.WORKING, TaskState.FAILED, TaskState.CANCELED}),
}


class InvalidTransition(Exception):
    """A state change the A2A Task lifecycle does not allow (e.g. leaving a terminal state)."""


def new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(6)}"


@dataclass
class PendingInput:
    """What the bridge needs to retry the MCP request after the pause. Never serialized."""

    tool: str
    arguments: dict[str, Any]
    input_key: str
    request_state: str
    allowed: list[str]


@dataclass
class Task:
    id: str
    context_id: str
    state: TaskState = TaskState.SUBMITTED
    status_message: dict[str, Any] | None = None
    history: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    # Bridge-private state: excluded from to_wire() on purpose.
    pending: PendingInput | None = None
    policy_version: str | None = None
    trace_id: str | None = None
    trace_context: otel_context.Context | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES

    def agent_message(self, text: str) -> dict[str, Any]:
        return {
            "messageId": new_id("msg"),
            "role": "ROLE_AGENT",
            "parts": [{"text": text}],
            "taskId": self.id,
            "contextId": self.context_id,
        }

    def add_user_message(self, message: dict[str, Any]) -> None:
        self.history.append(message)

    def transition(self, new_state: TaskState, text: str | None = None) -> None:
        if new_state != self.state and new_state not in _TRANSITIONS.get(self.state, frozenset()):
            raise InvalidTransition(f"Task {self.id}: {self.state} -> {new_state} is not allowed")
        previous = self.state
        self.state = new_state
        if text is not None:
            message = self.agent_message(text)
            self.status_message = message
            self.history.append(message)
        if previous != new_state:
            metrics.A2A_TASKS_BY_STATE.labels(state=previous.value).dec()
            metrics.A2A_TASKS_BY_STATE.labels(state=new_state.value).inc()
            if new_state in TERMINAL_STATES:
                metrics.A2A_TASKS.labels(final_state=new_state.value).inc()
        logger.info(
            "task %s: %s -> %s",
            self.id,
            previous.value,
            new_state.value,
            extra={
                "event": "task_transition",
                "task_id": self.id,
                "context_id": self.context_id,
                "task_state": new_state.value,
                "previous_state": previous.value,
            },
        )

    def repeat_status(self) -> None:
        """Re-send the current status text as a new agent message (same state, same text)."""
        if self.status_message is None:
            return
        text = self.status_message["parts"][0]["text"]
        message = self.agent_message(text)
        self.status_message = message
        self.history.append(message)

    def add_artifact(self, name: str, text: str) -> None:
        self.artifacts.append({"artifactId": new_id("art"), "name": name, "parts": [{"text": text}]})

    def to_wire(self) -> dict[str, Any]:
        status: dict[str, Any] = {"state": self.state.value}
        if self.status_message is not None:
            status["message"] = self.status_message
        return {
            "id": self.id,
            "contextId": self.context_id,
            "status": status,
            "history": list(self.history),
            "artifacts": list(self.artifacts),
        }


class TaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}

    def create(self, context_id: str | None = None) -> Task:
        task = Task(id=new_id("task"), context_id=context_id or new_id("ctx"))
        self._tasks[task.id] = task
        metrics.A2A_TASKS_BY_STATE.labels(state=TaskState.SUBMITTED.value).inc()
        return task

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def __len__(self) -> int:
        return len(self._tasks)
