"""Helpers for the end-to-end tests. They talk to the stack started by `make up`."""

from __future__ import annotations

import copy
import json
import os
import secrets
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
WIRE = ROOT / "exemplos" / "wire"
AGENT_URL = os.environ.get("AGENT_URL", "http://localhost:7300").rstrip("/")
MCP_URL = os.environ.get("MCP_URL", "http://localhost:7301").rstrip("/")
JAEGER_URL = os.environ.get("JAEGER_URL", "http://localhost:16686").rstrip("/")
LOKI_URL = os.environ.get("LOKI_URL", "http://localhost:3100").rstrip("/")
GRAFANA_URL = os.environ.get("GRAFANA_URL", "http://localhost:3000").rstrip("/")
PROTOCOL = "2026-07-28"


def wire(name: str) -> dict[str, Any]:
    return json.loads((WIRE / name).read_text(encoding="utf-8"))


def new_traceparent() -> tuple[str, str]:
    trace_id = secrets.token_hex(16)
    return f"00-{trace_id}-{secrets.token_hex(8)}-01", trace_id


def compose(*args: str, timeout: int = 180) -> str:
    result = subprocess.run(
        ["docker", "compose", *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(f"docker compose {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def restore() -> None:
    compose("up", "-d", "--force-recreate", "--wait", "--wait-timeout", "120", "mcp-server", "agent")


def mcp_log_lines(since: str) -> list[dict[str, Any]]:
    """JSON request lines the MCP server wrote to stderr since an ISO timestamp."""
    out = compose("logs", "--no-color", "--no-log-prefix", "--since", since, "mcp-server")
    rows = []
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("{") and '"mcp_server.requests"' in line:
            rows.append(json.loads(line))
    return rows


def eventually(check: Callable[[], Any], timeout: float = 45, interval: float = 2, what: str = "condition") -> Any:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            value = check()
            if value:
                return value
        except Exception as exc:  # noqa: BLE001 - retried until the deadline
            last_error = exc
        time.sleep(interval)
    raise AssertionError(f"timed out waiting for {what}" + (f": {last_error}" if last_error else ""))


def env_value(key: str, default: str = "") -> str:
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{key}=") and line.split("=", 1)[1]:
                return line.split("=", 1)[1]
    return os.environ.get(key, default)


class A2A:
    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def rpc(self, method: str, params: dict[str, Any], traceparent: str | None = None) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if traceparent:
            headers["traceparent"] = traceparent
        body = {"jsonrpc": "2.0", "id": secrets.token_hex(4), "method": method, "params": params}
        response = self.client.post(f"{AGENT_URL}/a2a", json=body, headers=headers)
        response.raise_for_status()
        return response.json()

    def send(self, text: str, task_id: str | None = None, traceparent: str | None = None) -> dict[str, Any]:
        message: dict[str, Any] = {
            "messageId": f"msg-{secrets.token_hex(6)}",
            "role": "ROLE_USER",
            "parts": [{"text": text}],
        }
        if task_id:
            message["taskId"] = task_id
        return self.rpc("SendMessage", {"message": message}, traceparent)

    def get(self, task_id: str) -> dict[str, Any]:
        return self.rpc("GetTask", {"id": task_id})


class MCP:
    def __init__(self, client: httpx.Client) -> None:
        self.client = client

    def post(self, body: dict[str, Any], headers: dict[str, str] | None = None) -> httpx.Response:
        sent = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": PROTOCOL,
            "Mcp-Method": body["method"],
        }
        name = body["params"].get("name") or body["params"].get("uri")
        if name:
            sent["Mcp-Name"] = name
        sent.update(headers or {})
        return self.client.post(f"{MCP_URL}/mcp", json=body, headers=sent)

    def wire_call(self, name: str, **changes: Any) -> httpx.Response:
        body = copy.deepcopy(wire(name)["request"]["body"])
        body["id"] = secrets.token_hex(4)
        body["params"].update(changes)
        return self.post(body)


def task_of(response: dict[str, Any]) -> dict[str, Any]:
    assert "result" in response, f"expected a result, got {response}"
    return response["result"]["task"]


def state(task: dict[str, Any]) -> str:
    return task["status"]["state"]


def status_text(task: dict[str, Any]) -> str:
    return " ".join(p.get("text", "") for p in task["status"]["message"]["parts"])


def artifact_json(task: dict[str, Any]) -> dict[str, Any]:
    (artifact,) = task["artifacts"]
    assert artifact["name"] == "reserva"
    return json.loads(artifact["parts"][0]["text"])


@pytest.fixture(scope="session")
def http() -> httpx.Client:
    with httpx.Client(timeout=30) as client:
        yield client


@pytest.fixture
def a2a(http) -> A2A:
    return A2A(http)


@pytest.fixture
def mcp(http) -> MCP:
    return MCP(http)


@pytest.fixture
def fresh_stack() -> None:
    """Fresh agent and MCP server: the evaluator flows assume the initial data of dados/."""
    restore()
