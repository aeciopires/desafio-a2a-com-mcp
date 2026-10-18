"""Room-booking rules. Pure functions only: no I/O, no protocol, easy to unit test.

The messages below are part of the challenge contract and must not change.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone

POLICY_TZ = timezone(timedelta(hours=-3))
WINDOW_START = time(8, 0)
WINDOW_END = time(20, 0)
MAX_DURATION = timedelta(hours=2)
MAX_ALTERNATIVES = 3

MSG_UNKNOWN_ROOM = "Sala inexistente: {room}"
MSG_OUTSIDE_WINDOW = "Fora da janela de uso: a politica permite reservas entre 08:00 e 20:00"
MSG_TOO_LONG = "Duracao acima do limite: a politica permite no maximo 2 horas"
MSG_INVALID_INTERVAL = "Intervalo invalido: fim deve ser posterior a inicio"
MSG_NO_ALTERNATIVES = "Sem alternativas disponiveis no intervalo"
MSG_INVALID_DATETIME = "Data invalida: {value} (use ISO 8601 com fuso, ex.: 2026-11-03T14:00:00-03:00)"


class DomainError(Exception):
    """A request broke a booking rule. `reason` is a stable slug used in metrics."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


@dataclass(frozen=True)
class Room:
    id: str
    nome: str
    capacidade: int
    recursos: tuple[str, ...]


@dataclass(frozen=True)
class Reservation:
    id: str
    sala: str
    inicio: str
    fim: str
    responsavel: str

    @property
    def start(self) -> datetime:
        return parse_instant(self.inicio)

    @property
    def end(self) -> datetime:
        return parse_instant(self.fim)


@dataclass(frozen=True)
class ValidRequest:
    room: Room
    start: datetime
    end: datetime


def parse_instant(value: str) -> datetime:
    """Parse an ISO 8601 timestamp that must carry an explicit UTC offset."""
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise DomainError("data_invalida", MSG_INVALID_DATETIME.format(value=value)) from exc
    if parsed.tzinfo is None:
        raise DomainError("data_invalida", MSG_INVALID_DATETIME.format(value=value))
    return parsed


def validate_request(rooms: dict[str, Room], room_id: str, inicio: str, fim: str) -> ValidRequest:
    """Apply the usage policy in a fixed order: room, interval, window, duration."""
    room = rooms.get(room_id)
    if room is None:
        raise DomainError("sala_inexistente", MSG_UNKNOWN_ROOM.format(room=room_id))

    start = parse_instant(inicio)
    end = parse_instant(fim)
    if end <= start:
        raise DomainError("intervalo", MSG_INVALID_INTERVAL)

    local_start = start.astimezone(POLICY_TZ)
    local_end = end.astimezone(POLICY_TZ)
    same_day = local_start.date() == local_end.date()
    if not (same_day and local_start.time() >= WINDOW_START and local_end.time() <= WINDOW_END):
        raise DomainError("janela", MSG_OUTSIDE_WINDOW)

    if end - start > MAX_DURATION:
        raise DomainError("duracao", MSG_TOO_LONG)

    return ValidRequest(room=room, start=start, end=end)


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    """Half-open intervals: back-to-back bookings do not overlap."""
    return a_start < b_end and b_start < a_end


def conflicts(reservations: Iterable[Reservation], room_id: str, start: datetime, end: datetime) -> list[Reservation]:
    return [r for r in reservations if r.sala == room_id and overlaps(start, end, r.start, r.end)]


def alternatives(
    rooms: dict[str, Room],
    reservations: Sequence[Reservation],
    requested: Room,
    start: datetime,
    end: datetime,
    limit: int = MAX_ALTERNATIVES,
) -> list[str]:
    """Free rooms with capacity >= the requested one, by (capacity, id), at most `limit`."""
    candidates = [
        room
        for room in rooms.values()
        if room.id != requested.id
        and room.capacidade >= requested.capacidade
        and not conflicts(reservations, room.id, start, end)
    ]
    candidates.sort(key=lambda room: (room.capacidade, room.id))
    return [room.id for room in candidates[:limit]]


def parse_policy_version(text: str) -> str:
    """Extract the version declared on the first line (`versao: 2026-11-01`)."""
    first_line = text.lstrip().splitlines()[0] if text.strip() else ""
    key, _, value = first_line.partition(":")
    if key.strip().lower() != "versao" or not value.strip():
        raise ValueError(f"policy file must start with 'versao: <value>', got {first_line!r}")
    return value.strip()
