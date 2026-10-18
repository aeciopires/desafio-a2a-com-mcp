"""Bridge guarantees beyond the evaluator script: terminal states, isolation, no leaks, determinism."""

from __future__ import annotations

import json
import re

from conftest import artifact_json, state, status_text, task_of


def h(hour: str, day: str = "2026-11-03") -> str:
    return f"{day}T{hour}:00-03:00"


def booking(room: str, start: str, end: str, who: str) -> str:
    return f"reservar sala={room} inicio={start} fim={end} responsavel={who}"


def test_terminal_task_rejects_new_messages(a2a):
    done = task_of(a2a.send(booking("sala-aquario", h("08:00", "2026-11-10"), h("09:00", "2026-11-10"), "Doc")))
    assert state(done) == "TASK_STATE_COMPLETED"
    response = a2a.send("escolha=sala-fusca", done["id"])
    assert "error" in response
    assert state(task_of(a2a.get(done["id"]))) == "TASK_STATE_COMPLETED"


def test_invalid_choice_keeps_the_pause_and_repeats_the_question(fresh_stack, a2a):
    paused = task_of(a2a.send(booking("sala-garagem", h("14:00"), h("15:00"), "Marty")))
    again = task_of(a2a.send("escolha=sala-aquario", paused["id"]))
    assert state(again) == "TASK_STATE_INPUT_REQUIRED"
    assert status_text(again) == status_text(paused)


def test_two_paused_tasks_finish_with_their_own_reservations(fresh_stack, a2a):
    a = task_of(a2a.send(booking("sala-fusca", h("16:00"), h("17:00"), "Lorraine")))
    b = task_of(a2a.send(booking("sala-garagem", h("14:00"), h("15:00"), "George")))
    assert state(a) == state(b) == "TASK_STATE_INPUT_REQUIRED"
    done_b = task_of(a2a.send("escolha=sala-mirante", b["id"]))
    done_a = task_of(a2a.send("escolha=sala-mirante", a["id"]))
    ra, rb = artifact_json(done_a), artifact_json(done_b)
    assert (ra["responsavel"], ra["inicio"]) == ("Lorraine", h("16:00"))
    assert (rb["responsavel"], rb["inicio"]) == ("George", h("14:00"))
    assert ra["reserva"] != rb["reserva"]


SEALED_TOKEN = re.compile(r"v1\.[A-Za-z0-9_-]{40,}")


def test_request_state_never_reaches_the_a2a_client(fresh_stack, a2a):
    paused = a2a.send(booking("sala-garagem", h("14:00"), h("15:00"), "Marty"))
    task_id = task_of(paused)["id"]
    responses = [paused, a2a.get(task_id), a2a.send("escolha=sala-fusca", task_id), a2a.get(task_id)]
    for body in responses:
        text = json.dumps(body)
        assert "requestState" not in text
        assert not SEALED_TOKEN.search(text), "a sealed requestState token leaked into an A2A response"


def test_same_request_same_pause(fresh_stack, a2a):
    text = booking("sala-garagem", h("14:00"), h("15:00"), "Marty")
    first, second = task_of(a2a.send(text)), task_of(a2a.send(text))
    assert status_text(first) == status_text(second) == "alternativas: sala-fusca, sala-mirante"
    assert first["id"] != second["id"]
