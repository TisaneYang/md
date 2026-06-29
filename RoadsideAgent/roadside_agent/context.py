from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .types import RoadsideDecision


@dataclass
class RoadsideContextEntry:
    tick: int
    timestamp: float
    global_summary: str
    sent_messages: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "timestamp": self.timestamp,
            "global_summary": self.global_summary,
            "sent_messages": self.sent_messages,
        }


class RoadsideContext:
    def __init__(self, window_size: int = 8) -> None:
        self.window_size = max(1, int(window_size))
        self._entries: list[RoadsideContextEntry] = []

    def append(
        self,
        tick: int,
        timestamp: float,
        decision: RoadsideDecision,
        send_results: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        self._entries.append(
            RoadsideContextEntry(
                tick=tick,
                timestamp=timestamp,
                global_summary=decision.global_summary,
                sent_messages=list(send_results or []),
            )
        )
        if len(self._entries) > self.window_size:
            self._entries = self._entries[-self.window_size :]

    def snapshot(self) -> list[dict[str, Any]]:
        return [entry.to_dict() for entry in self._entries]
