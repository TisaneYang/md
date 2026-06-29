from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .types import RoadsideBatchInput, RoadsideDecision


class RoadsideLogger:
    def __init__(self, path: str, enabled: bool = True) -> None:
        self.path = Path(path)
        self.enabled = enabled

    def log_tick(
        self,
        tick: int,
        timestamp: float,
        batch_input: Optional[RoadsideBatchInput],
        decision: Optional[RoadsideDecision],
        send_results: Optional[list[dict[str, Any]]] = None,
        fallback_reason: Optional[str] = None,
    ) -> None:
        if not self.enabled:
            return

        self.path.parent.mkdir(parents=True, exist_ok=True)
        record: dict[str, Any] = {
            "tick": tick,
            "timestamp": timestamp,
            "batch_input": None if batch_input is None else batch_input.to_dict(),
            "decision": None if decision is None else decision.to_dict(),
            "send_results": send_results or [],
            "fallback_reason": fallback_reason,
        }
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
