"""Fixed-format request parsing. No natural language, no LLM: same text, same result."""

from __future__ import annotations

import re
from dataclasses import dataclass

BOOKING_FORMAT = "reservar sala=<id> inicio=<iso8601> fim=<iso8601> responsavel=<nome>"
CHOICE_FORMAT = "escolha=<id da sala> ou escolha=recusar"
DECLINE = "recusar"

_BOOKING = re.compile(
    r"^\s*reservar\s+sala=(?P<sala>\S+)\s+inicio=(?P<inicio>\S+)\s+fim=(?P<fim>\S+)\s+responsavel=(?P<responsavel>.+?)\s*$"
)
_CHOICE = re.compile(r"^\s*escolha=(?P<valor>\S+)\s*$")


class ParseError(ValueError):
    """The text does not follow the fixed format. The message shows the expected one."""


@dataclass(frozen=True)
class BookingRequest:
    sala: str
    inicio: str
    fim: str
    responsavel: str

    def as_arguments(self) -> dict[str, str]:
        return {"sala": self.sala, "inicio": self.inicio, "fim": self.fim, "responsavel": self.responsavel}


def parse_booking(text: str) -> BookingRequest:
    match = _BOOKING.match(text or "")
    if not match:
        raise ParseError(f"Pedido fora do formato. Use: {BOOKING_FORMAT}")
    return BookingRequest(**match.groupdict())


def parse_choice(text: str) -> str | None:
    """The value after `escolha=`, or None when the text is not a choice at all."""
    match = _CHOICE.match(text or "")
    return match.group("valor") if match else None
