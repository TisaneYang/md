from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .types import PilotDecision, UpstreamCommand


class PilotLogger:
    def __init__(self, path: str, enabled: bool = True) -> None:
        self.enabled = enabled
        self.path = Path(path)
        if self.enabled:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def log_tick(
        self,
        tick: int,
        timestamp: float,
        upstream: Optional[UpstreamCommand],
        decision: Optional[PilotDecision],
        model_debug: Optional[dict[str, Any]] = None,
        fallback_reason: Optional[str] = None,
    ) -> None:
        if not self.enabled:
            return

        record = {
            "tick": tick,
            "timestamp": timestamp,
            "upstream": None if upstream is None else upstream.to_dict(),
            "pilot_decision": None if decision is None else decision.to_dict(),
            "model_debug": model_debug or {},
            "fallback_reason": fallback_reason,
        }
        with self.path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

