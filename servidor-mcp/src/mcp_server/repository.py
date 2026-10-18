"""In-memory store for rooms and reservations, seeded from dados/ at startup.

Reservations created at runtime live only in this process: a restart restores
the initial data (that is what `make restore` relies on).
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path

from mcp_server.domain import Reservation, Room

_RESERVATION_ID = re.compile(r"^res-(\d+)$")


class Repository:
    def __init__(self, rooms: list[Room], reservations: list[Reservation], policy_text: str) -> None:
        self._rooms = {room.id: room for room in rooms}
        self._reservations = list(reservations)
        self._lock = threading.Lock()
        self._last_id = max((self._number(r.id) for r in reservations), default=0)
        self.policy_text = policy_text

    @staticmethod
    def _number(reservation_id: str) -> int:
        match = _RESERVATION_ID.match(reservation_id)
        return int(match.group(1)) if match else 0

    @classmethod
    def from_data_dir(cls, data_dir: Path) -> Repository:
        rooms_raw = json.loads((data_dir / "salas.json").read_text(encoding="utf-8"))
        reservations_raw = json.loads((data_dir / "reservas.json").read_text(encoding="utf-8"))
        policy_text = (data_dir / "politica-de-uso.md").read_text(encoding="utf-8")
        rooms = [
            Room(id=r["id"], nome=r["nome"], capacidade=int(r["capacidade"]), recursos=tuple(r["recursos"]))
            for r in rooms_raw
        ]
        reservations = [
            Reservation(id=r["id"], sala=r["sala"], inicio=r["inicio"], fim=r["fim"], responsavel=r["responsavel"])
            for r in reservations_raw
        ]
        return cls(rooms, reservations, policy_text)

    @property
    def rooms(self) -> dict[str, Room]:
        return self._rooms

    def reservations(self) -> list[Reservation]:
        with self._lock:
            return list(self._reservations)

    def add(self, sala: str, inicio: str, fim: str, responsavel: str) -> Reservation:
        with self._lock:
            self._last_id += 1
            reservation = Reservation(
                id=f"res-{self._last_id:04d}", sala=sala, inicio=inicio, fim=fim, responsavel=responsavel
            )
            self._reservations.append(reservation)
            return reservation
