from __future__ import annotations

import pytest

from agent import tracing
from agent.bridge import allowed_choices, alternatives_line, extract_policy_version
from agent.card import build_agent_card
from agent.parser import ParseError, parse_booking, parse_choice
from agent.tasks import InvalidTransition, PendingInput, Task, TaskState, TaskStore


def test_booking_request_is_parsed():
    request = parse_booking(
        "reservar sala=sala-garagem inicio=2026-11-03T14:00:00-03:00 "
        "fim=2026-11-03T15:00:00-03:00 responsavel=Marty McFly"
    )
    assert request.as_arguments() == {
        "sala": "sala-garagem",
        "inicio": "2026-11-03T14:00:00-03:00",
        "fim": "2026-11-03T15:00:00-03:00",
        "responsavel": "Marty McFly",
    }


@pytest.mark.parametrize("text", ["", "reservar a sala garagem", "reservar sala=x inicio=y fim=z"])
def test_malformed_booking_shows_the_expected_format(text):
    with pytest.raises(ParseError, match="reservar sala=<id>"):
        parse_booking(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [("escolha=sala-fusca", "sala-fusca"), (" escolha=recusar ", "recusar"), ("sala-fusca", None), ("escolha=", None)],
)
def test_choice_parsing(text, expected):
    assert parse_choice(text) == expected


def test_alternatives_line_is_exact():
    assert alternatives_line(["sala-fusca", "sala-mirante"]) == "alternativas: sala-fusca, sala-mirante"


def test_allowed_choices_accepts_enum_and_const():
    assert allowed_choices({"properties": {"sala": {"enum": ["a", "b"]}}}) == ["a", "b"]
    assert allowed_choices({"properties": {"sala": {"const": "a"}}}) == ["a"]


def test_policy_version_is_read_from_first_line():
    assert extract_policy_version("versao: 2026-11-01\n\n- x") == "2026-11-01"


def test_task_lifecycle_and_terminal_states_are_final():
    task = TaskStore().create()
    assert task.state is TaskState.SUBMITTED
    task.transition(TaskState.WORKING)
    task.transition(TaskState.INPUT_REQUIRED, "alternativas: a")
    task.transition(TaskState.WORKING)
    task.transition(TaskState.COMPLETED, "ok")
    assert task.is_terminal
    with pytest.raises(InvalidTransition):
        task.transition(TaskState.WORKING)


def test_submitted_cannot_jump_to_completed():
    with pytest.raises(InvalidTransition):
        Task(id="t", context_id="c").transition(TaskState.COMPLETED)


def test_wire_form_never_includes_bridge_state():
    task = Task(id="task-1", context_id="ctx-1")
    task.pending = PendingInput("reservar_sala", {}, "k", "v1.SECRET-STATE", ["a"])
    task.policy_version = "2026-11-01"
    wire = task.to_wire()
    assert set(wire) == {"id", "contextId", "status", "history", "artifacts"}
    assert "SECRET-STATE" not in str(wire)


def test_traceparent_parsing():
    assert tracing.parse_traceparent("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01") == (
        "4bf92f3577b34da6a3ce929d0e0e4736",
        "00f067aa0ba902b7",
    )
    assert tracing.parse_traceparent("garbage") is None
    assert tracing.parse_traceparent("00-00000000000000000000000000000000-00f067aa0ba902b7-01") is None


def test_outbound_traceparent_keeps_trace_id_without_a_recording_span():
    token = tracing.current_trace_id.set("4bf92f3577b34da6a3ce929d0e0e4736")
    try:
        first, second = tracing.outbound_traceparent(), tracing.outbound_traceparent()
    finally:
        tracing.current_trace_id.reset(token)
    assert first.split("-")[1] == second.split("-")[1] == "4bf92f3577b34da6a3ce929d0e0e4736"
    assert first.split("-")[2] != second.split("-")[2]


def test_agent_card_matches_v1_shape():
    card = build_agent_card("http://127.0.0.1:7300/a2a", "0.1.0")
    assert card["supportedInterfaces"] == [
        {"url": "http://127.0.0.1:7300/a2a", "protocolBinding": "JSONRPC", "protocolVersion": "1.0"}
    ]
    assert [s["id"] for s in card["skills"]] == ["reservar-sala"]
    assert card["version"] == "0.1.0"
