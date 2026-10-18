"""The bridge end to end inside the agent: A2A JSON-RPC in, scripted MCP server out."""

from __future__ import annotations

import json

import httpx
import pytest
from tests.conftest import INPUT_KEY, MCP_URL, REQUEST_STATE, booked, input_required, tool_error

from agent.app import create_app
from agent.config import load_settings

TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
CONFLICT = "reservar sala=sala-garagem inicio=2026-11-03T14:00:00-03:00 fim=2026-11-03T15:00:00-03:00 responsavel=Marty"


@pytest.fixture
async def a2a(monkeypatch, fake_mcp):
    monkeypatch.setenv("MCP_URL", MCP_URL)
    app = create_app(load_settings())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://agent.test") as client:
        yield client


async def send(client, text, task_id=None, traceparent=None):
    message = {"messageId": "m1", "role": "ROLE_USER", "parts": [{"text": text}]}
    if task_id:
        message["taskId"] = task_id
    headers = {"traceparent": traceparent} if traceparent else {}
    response = await client.post(
        "/a2a",
        json={"jsonrpc": "2.0", "id": 1, "method": "SendMessage", "params": {"message": message}},
        headers=headers,
    )
    return response.json()


def task_of(body):
    return body["result"]["task"]


def status_text(task):
    return task["status"]["message"]["parts"][0]["text"]


async def test_card_is_served(a2a):
    card = (await a2a.get("/.well-known/agent-card.json")).json()
    assert card["skills"][0]["id"] == "reservar-sala"


async def test_free_room_completes_with_reservation_artifact(a2a, fake_mcp):
    fake_mcp.tool_results = [booked("sala-garagem")]
    task = task_of(await send(a2a, CONFLICT))
    assert task["status"]["state"] == "TASK_STATE_COMPLETED"
    artifact = task["artifacts"][0]
    assert artifact["name"] == "reserva"
    assert json.loads(artifact["parts"][0]["text"]) == {
        "reserva": "res-0003",
        "sala": "sala-garagem",
        "inicio": "2026-11-03T14:00:00-03:00",
        "fim": "2026-11-03T15:00:00-03:00",
        "responsavel": "Marty",
        "politica": "2026-11-01",
    }
    # Runtime discovery happens before the first tools/call.
    assert [r["method"] for r in fake_mcp.requests] == ["tools/list", "resources/read", "tools/call"]


async def test_every_mcp_request_carries_meta_headers_and_new_ids(a2a, fake_mcp):
    fake_mcp.tool_results = [input_required(["sala-fusca", "sala-mirante"]), booked("sala-fusca")]
    task = task_of(await send(a2a, CONFLICT, traceparent=TRACEPARENT))
    await send(a2a, "escolha=sala-fusca", task["id"])  # continuation without traceparent header

    ids = [r["id"] for r in fake_mcp.requests]
    assert len(ids) == len(set(ids))
    for body, headers in zip(fake_mcp.requests, fake_mcp.headers, strict=True):
        meta = body["params"]["_meta"]
        assert meta["io.modelcontextprotocol/protocolVersion"] == "2026-07-28"
        assert meta["io.modelcontextprotocol/clientCapabilities"] == {"elicitation": {"form": {}}}
        assert meta["traceparent"].split("-")[1] == "4bf92f3577b34da6a3ce929d0e0e4736"
        assert headers["MCP-Protocol-Version"] == "2026-07-28"
        assert headers["Mcp-Method"] == body["method"]
        if body["method"] == "tools/call":
            assert headers["Mcp-Name"] == body["params"]["name"]
        if body["method"] == "resources/read":
            assert headers["Mcp-Name"] == body["params"]["uri"]


async def test_conflict_pauses_then_choice_retries_with_echoed_state(a2a, fake_mcp):
    fake_mcp.tool_results = [input_required(["sala-fusca", "sala-mirante"]), booked("sala-mirante", "res-0005")]
    paused = task_of(await send(a2a, CONFLICT))
    assert paused["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"
    assert status_text(paused) == "alternativas: sala-fusca, sala-mirante"

    done = task_of(await send(a2a, "escolha=sala-mirante", paused["id"]))
    assert done["status"]["state"] == "TASK_STATE_COMPLETED"
    first, retry = fake_mcp.calls("tools/call")
    assert retry["id"] != first["id"]
    assert retry["params"]["arguments"] == first["params"]["arguments"]
    assert retry["params"]["requestState"] == REQUEST_STATE
    assert retry["params"]["inputResponses"] == {INPUT_KEY: {"action": "accept", "content": {"sala": "sala-mirante"}}}


async def test_single_alternative_as_const(a2a, fake_mcp):
    fake_mcp.tool_results = [input_required(["sala-mirante"])]
    paused = task_of(await send(a2a, CONFLICT))
    assert status_text(paused) == "alternativas: sala-mirante"


async def test_invalid_choice_keeps_the_task_paused_without_calling_mcp(a2a, fake_mcp):
    fake_mcp.tool_results = [input_required(["sala-fusca", "sala-mirante"])]
    paused = task_of(await send(a2a, CONFLICT))
    again = task_of(await send(a2a, "escolha=sala-aquario", paused["id"]))
    assert again["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"
    assert status_text(again) == "alternativas: sala-fusca, sala-mirante"
    assert len(fake_mcp.calls("tools/call")) == 1


async def test_decline_cancels_the_task(a2a, fake_mcp):
    declined = {"reserva": None, "reservado": False, "motivo": "recusado"}
    fake_mcp.tool_results = [input_required(["sala-mirante"]), {**booked("x"), "structuredContent": declined}]
    paused = task_of(await send(a2a, CONFLICT))
    done = task_of(await send(a2a, "escolha=recusar", paused["id"]))
    assert done["status"]["state"] == "TASK_STATE_CANCELED"
    assert fake_mcp.calls("tools/call")[1]["params"]["inputResponses"] == {INPUT_KEY: {"action": "decline"}}


async def test_tool_error_fails_the_task_with_the_exact_message(a2a, fake_mcp):
    message = "Error executing tool reservar_sala: Sala inexistente: sala-delorean"
    fake_mcp.tool_results = [tool_error(message)]
    task = task_of(await send(a2a, CONFLICT.replace("sala-garagem", "sala-delorean")))
    assert task["status"]["state"] == "TASK_STATE_FAILED"
    assert status_text(task) == message
    assert any(message in m["parts"][0]["text"] for m in task["history"])


async def test_mcp_protocol_error_fails_the_task(a2a, fake_mcp):
    fake_mcp.tool_results = [
        input_required(["sala-fusca"]),
        (400, {"code": -32602, "message": "Invalid or expired requestState"}),
    ]
    paused = task_of(await send(a2a, CONFLICT))
    failed = task_of(await send(a2a, "escolha=sala-fusca", paused["id"]))
    assert failed["status"]["state"] == "TASK_STATE_FAILED"
    assert "-32602" in status_text(failed)


async def test_terminal_task_rejects_new_messages(a2a, fake_mcp):
    fake_mcp.tool_results = [booked("sala-garagem")]
    task = task_of(await send(a2a, CONFLICT))
    body = await send(a2a, "escolha=sala-fusca", task["id"])
    assert body["error"]["code"] == -32004


async def test_unknown_task_and_method(a2a):
    assert (await send(a2a, "escolha=x", "task-nope"))["error"]["code"] == -32001
    response = await a2a.post("/a2a", json={"jsonrpc": "2.0", "id": 1, "method": "Nope", "params": {}})
    assert response.json()["error"]["code"] == -32601
    response = await a2a.post("/a2a", content=b"{not json")
    assert response.json()["error"]["code"] == -32700


async def test_get_task_reflects_current_state(a2a, fake_mcp):
    fake_mcp.tool_results = [input_required(["sala-fusca"])]
    paused = task_of(await send(a2a, CONFLICT))
    response = await a2a.post(
        "/a2a", json={"jsonrpc": "2.0", "id": 2, "method": "GetTask", "params": {"id": paused["id"]}}
    )
    task = task_of(response.json())
    assert (task["id"], task["contextId"]) == (paused["id"], paused["contextId"])
    assert task["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"


async def test_two_paused_tasks_keep_their_own_request_state(a2a, fake_mcp):
    other_state = REQUEST_STATE + "-other"
    fake_mcp.tool_results = [
        input_required(["sala-mirante"]),
        {**input_required(["sala-mirante"]), "requestState": other_state},
        booked("sala-mirante", "res-0010"),
        booked("sala-mirante", "res-0011"),
    ]
    a = task_of(await send(a2a, CONFLICT))
    b = task_of(await send(a2a, CONFLICT.replace("Marty", "George")))
    await send(a2a, "escolha=sala-mirante", b["id"])
    await send(a2a, "escolha=sala-mirante", a["id"])
    retries = fake_mcp.calls("tools/call")[2:]
    assert [r["params"]["requestState"] for r in retries] == [other_state, REQUEST_STATE]
    assert retries[0]["params"]["arguments"]["responsavel"] == "George"


async def test_request_state_never_appears_in_a2a_responses(a2a, fake_mcp):
    fake_mcp.tool_results = [input_required(["sala-fusca"]), booked("sala-fusca")]
    first = await send(a2a, CONFLICT)
    get = await a2a.post(
        "/a2a", json={"jsonrpc": "2.0", "id": 2, "method": "GetTask", "params": {"id": task_of(first)["id"]}}
    )
    last = await send(a2a, "escolha=sala-fusca", task_of(first)["id"])
    for body in (first, get.json(), last):
        assert REQUEST_STATE not in json.dumps(body)


async def test_unreachable_mcp_fails_the_task_with_a_clear_message(monkeypatch):
    monkeypatch.setenv("MCP_URL", "http://127.0.0.1:9/mcp")
    monkeypatch.setenv("MCP_TIMEOUT_SECONDS", "1")
    app = create_app(load_settings())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://agent.test") as client:
        task = task_of(await send(client, CONFLICT))
    assert task["status"]["state"] == "TASK_STATE_FAILED"
    assert "MCP server unreachable at http://127.0.0.1:9/mcp" in status_text(task)
