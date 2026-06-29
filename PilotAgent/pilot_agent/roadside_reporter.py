from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional

from .config import RoadsideReportConfig
from .types import PilotDecision, UpstreamCommand


class RoadsideReporter:
    def __init__(self, config: RoadsideReportConfig) -> None:
        self.enabled = bool(config.enabled)
        self.url = config.url
        self.endpoint = config.endpoint
        self.timeout = config.timeout_ms / 1000.0

    def report_decision(
        self,
        vehicle_id: Optional[str],
        timestamp: float,
        upstream: Optional[UpstreamCommand],
        decision: PilotDecision,
    ) -> None:
        if not self.enabled or not vehicle_id or not self.endpoint:
            return
        payload = {
            "vehicle_id": str(vehicle_id),
            "timestamp": float(timestamp),
            "endpoint": self.endpoint,
            "upstream": {} if upstream is None else upstream.to_dict(),
            "task_status": decision.task_status,
        }
        self._post_json(payload)

    def report_heartbeat(
        self,
        vehicle_id: Optional[str],
        timestamp: float,
    ) -> None:
        if not self.enabled or not vehicle_id or not self.endpoint:
            return
        payload = {
            "vehicle_id": str(vehicle_id),
            "timestamp": float(timestamp),
            "endpoint": self.endpoint,
        }
        self._post_json(payload)

    def _post_json(self, payload: dict[str, object]) -> None:
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout):
                return
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Roadside report request failed: {exc}") from exc
