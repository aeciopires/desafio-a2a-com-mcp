from __future__ import annotations

import pytest

from mcp_server import domain
from mcp_server.domain import DomainError, Reservation, Room

ROOMS = {
    r.id: r
    for r in (
        Room("sala-aquario", "Aquario", 4, ("tv",)),
        Room("sala-porao", "Porao", 6, ("quadro",)),
        Room("sala-garagem", "Garagem", 12, ("tv", "quadro")),
        Room("sala-fusca", "Fusca", 12, ("tv",)),
        Room("sala-mirante", "Mirante", 20, ("tv", "quadro", "camera")),
    )
}
RESERVATIONS = [
    Reservation("res-0001", "sala-garagem", "2026-11-03T14:00:00-03:00", "2026-11-03T15:00:00-03:00", "Marty"),
    Reservation("res-0002", "sala-fusca", "2026-11-03T16:00:00-03:00", "2026-11-03T17:00:00-03:00", "Jennifer"),
]


def h(hour: str) -> str:
    return f"2026-11-03T{hour}:00-03:00"


def test_valid_request_returns_room_and_interval():
    request = domain.validate_request(ROOMS, "sala-aquario", h("09:00"), h("10:00"))
    assert request.room.id == "sala-aquario"
    assert (request.end - request.start).total_seconds() == 3600


@pytest.mark.parametrize(
    ("room", "start", "end", "reason", "message"),
    [
        ("sala-delorean", h("09:00"), h("10:00"), "sala_inexistente", "Sala inexistente: sala-delorean"),
        ("sala-aquario", h("10:00"), h("09:00"), "intervalo", domain.MSG_INVALID_INTERVAL),
        ("sala-aquario", h("10:00"), h("10:00"), "intervalo", domain.MSG_INVALID_INTERVAL),
        ("sala-aquario", h("07:00"), h("08:00"), "janela", domain.MSG_OUTSIDE_WINDOW),
        ("sala-aquario", h("19:30"), h("20:30"), "janela", domain.MSG_OUTSIDE_WINDOW),
        ("sala-aquario", h("09:00"), h("12:00"), "duracao", domain.MSG_TOO_LONG),
        ("sala-aquario", "amanha", h("10:00"), "data_invalida", "Data invalida: amanha"),
    ],
)
def test_validation_errors_carry_the_exact_messages(room, start, end, reason, message):
    with pytest.raises(DomainError) as excinfo:
        domain.validate_request(ROOMS, room, start, end)
    assert excinfo.value.reason == reason
    assert message in excinfo.value.message


def test_exact_contract_messages():
    assert domain.MSG_OUTSIDE_WINDOW == "Fora da janela de uso: a politica permite reservas entre 08:00 e 20:00"
    assert domain.MSG_TOO_LONG == "Duracao acima do limite: a politica permite no maximo 2 horas"
    assert domain.MSG_INVALID_INTERVAL == "Intervalo invalido: fim deve ser posterior a inicio"
    assert domain.MSG_NO_ALTERNATIVES == "Sem alternativas disponiveis no intervalo"


def test_unknown_room_is_checked_before_the_interval():
    with pytest.raises(DomainError) as excinfo:
        domain.validate_request(ROOMS, "sala-x", h("10:00"), h("09:00"))
    assert excinfo.value.reason == "sala_inexistente"


def test_window_edges_are_inclusive_and_policy_uses_sao_paulo_offset():
    domain.validate_request(ROOMS, "sala-aquario", h("08:00"), h("10:00"))
    domain.validate_request(ROOMS, "sala-aquario", h("18:00"), h("20:00"))
    # 11:00Z is 08:00 in -03:00
    domain.validate_request(ROOMS, "sala-aquario", "2026-11-03T11:00:00+00:00", "2026-11-03T12:00:00+00:00")


def test_naive_timestamps_are_rejected():
    with pytest.raises(DomainError):
        domain.validate_request(ROOMS, "sala-aquario", "2026-11-03T09:00:00", "2026-11-03T10:00:00")


def test_overlap_is_half_open():
    start, end = domain.parse_instant(h("14:00")), domain.parse_instant(h("15:00"))
    assert not domain.conflicts(
        RESERVATIONS, "sala-garagem", domain.parse_instant(h("15:00")), domain.parse_instant(h("16:00"))
    )
    assert domain.conflicts(RESERVATIONS, "sala-garagem", start, end)
    assert domain.conflicts(
        RESERVATIONS, "sala-garagem", domain.parse_instant(h("14:30")), domain.parse_instant(h("15:30"))
    )


def test_alternatives_follow_capacity_then_id_order():
    start, end = domain.parse_instant(h("14:00")), domain.parse_instant(h("15:00"))
    assert domain.alternatives(ROOMS, RESERVATIONS, ROOMS["sala-garagem"], start, end) == ["sala-fusca", "sala-mirante"]


def test_alternatives_tie_break_by_id_and_limit_to_three():
    start, end = domain.parse_instant(h("09:00")), domain.parse_instant(h("10:00"))
    found = domain.alternatives(ROOMS, RESERVATIONS, ROOMS["sala-aquario"], start, end)
    assert found == ["sala-porao", "sala-fusca", "sala-garagem"]


def test_alternatives_exclude_busy_and_smaller_rooms():
    start, end = domain.parse_instant(h("16:00")), domain.parse_instant(h("17:00"))
    busy = [*RESERVATIONS, Reservation("res-9", "sala-garagem", h("16:00"), h("17:00"), "x")]
    assert domain.alternatives(ROOMS, busy, ROOMS["sala-fusca"], start, end) == ["sala-mirante"]
    assert domain.alternatives(ROOMS, busy, ROOMS["sala-mirante"], start, end) == []


def test_policy_version_comes_from_the_first_line():
    assert domain.parse_policy_version("versao: 2026-11-01\n\n- regra") == "2026-11-01"
    with pytest.raises(ValueError):
        domain.parse_policy_version("sem versao\n")
