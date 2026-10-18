"""The evaluator flow (TASK.md, "Fluxo do avaliador"), step by step, against the running stack."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from conftest import (
    AGENT_URL,
    artifact_json,
    compose,
    mcp_log_lines,
    new_traceparent,
    state,
    status_text,
    task_of,
    wire,
)

GARAGEM_14H = wire("08-a2a-send-message.json")["request"]["body"]["params"]["message"]["parts"][0]["text"]


def test_step3_agent_card_matches_the_wire_example(http):
    card = http.get(f"{AGENT_URL}/.well-known/agent-card.json").json()
    expected = wire("07-a2a-agent-card.json")["response"]["body"]
    (interface,) = card["supportedInterfaces"]
    assert interface["protocolBinding"] == "JSONRPC"
    assert interface["protocolVersion"] == "1.0"
    assert interface["url"].endswith("/a2a")
    assert [s["id"] for s in card["skills"]] == ["reservar-sala"]
    assert card["capabilities"] == expected["capabilities"]
    assert card["defaultInputModes"] == expected["defaultInputModes"]


def test_steps_5_6_7_8_pause_then_choose(fresh_stack, a2a):
    since = datetime.now(UTC).isoformat()
    traceparent, trace_id = new_traceparent()

    paused = task_of(a2a.send(GARAGEM_14H, traceparent=traceparent))
    assert state(paused) == "TASK_STATE_INPUT_REQUIRED"
    assert status_text(paused) == "alternativas: sala-fusca, sala-mirante"
    assert state(task_of(a2a.get(paused["id"]))) == "TASK_STATE_INPUT_REQUIRED"

    done = task_of(a2a.send("escolha=sala-mirante", paused["id"], traceparent=traceparent))
    assert state(done) == "TASK_STATE_COMPLETED"
    reservation = artifact_json(task_of(a2a.get(paused["id"])))
    assert reservation["sala"] == "sala-mirante"
    assert reservation["politica"] == "2026-11-01"

    # Step 5: tools/list before the first tools/call, and the client's trace-id in _meta.
    rows = [r for r in mcp_log_lines(since) if r.get("traceparent") and trace_id in r["traceparent"]]
    methods = [r["method"] for r in rows]
    assert methods.index("tools/list") < methods.index("tools/call")
    # Step 6: the pair of tools/call around the pause uses different ids.
    calls = [r for r in rows if r["method"] == "tools/call"]
    assert [c["result_type"] for c in calls] == ["input_required", "complete"]
    assert calls[0]["id"] != calls[1]["id"]
    assert calls[1]["mrtr_action"] == "accept"


def test_step9_decline_cancels(fresh_stack, a2a):
    paused = task_of(a2a.send(GARAGEM_14H))
    assert state(paused) == "TASK_STATE_INPUT_REQUIRED"
    done = task_of(a2a.send("escolha=recusar", paused["id"]))
    assert state(done) == "TASK_STATE_CANCELED"
    assert done["artifacts"] == []


def test_step10_unknown_room_fails_with_the_tool_message(a2a):
    text = GARAGEM_14H.replace("sala-garagem", "sala-inexistente")
    task = task_of(a2a.send(text))
    assert state(task) == "TASK_STATE_FAILED"
    assert "Sala inexistente: sala-inexistente" in status_text(task)
    assert any("Sala inexistente: sala-inexistente" in m["parts"][0]["text"] for m in task["history"])


def _conflict_state(mcp) -> tuple[str, str]:
    response = mcp.wire_call("03-tools-call-conflito-input-required.json")
    result = response.json()["result"]
    assert result["resultType"] == "input_required"
    return next(iter(result["inputRequests"])), result["requestState"]


def test_step11_tampered_request_state_is_rejected(fresh_stack, mcp):
    key, request_state = _conflict_state(mcp)
    tampered = request_state[:-1] + ("A" if request_state[-1] != "A" else "B")
    response = mcp.wire_call(
        "04-tools-call-retry.json",
        inputResponses={key: {"action": "accept", "content": {"sala": "sala-fusca"}}},
        requestState=tampered,
    )
    assert response.json()["error"]["code"] == -32602


def test_step12_retry_survives_an_mcp_restart(fresh_stack, mcp):
    key, request_state = _conflict_state(mcp)
    compose("restart", "mcp-server")
    compose("up", "-d", "--wait", "--wait-timeout", "60", "mcp-server")
    response = mcp.wire_call(
        "04-tools-call-retry.json",
        inputResponses={key: {"action": "accept", "content": {"sala": "sala-fusca"}}},
        requestState=request_state,
    )
    result = response.json()["result"]
    assert result["resultType"] == "complete"
    assert result["structuredContent"]["sala"] == "sala-fusca"


def test_step13_conflict_without_elicitation_capability(mcp):
    body = wire("06-erro-32021-sem-elicitation.json")["request"]["body"]
    body["id"] = secrets.token_hex(4)
    response = mcp.post(body)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == -32021
    assert response.json()["error"]["data"]["requiredCapabilities"] == {"elicitation": {"form": {}}}


def test_decline_over_mcp_completes_without_error(fresh_stack, mcp):
    key, request_state = _conflict_state(mcp)
    response = mcp.wire_call(
        "04-tools-call-retry.json", inputResponses={key: {"action": "decline"}}, requestState=request_state
    )
    result = response.json()["result"]
    assert result["resultType"] == "complete"
    assert not result.get("isError")
    assert result["structuredContent"]["reservado"] is False
