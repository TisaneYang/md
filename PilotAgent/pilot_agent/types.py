from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class UpstreamCommand:
    timestamp: float
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "UpstreamCommand":
        if "timestamp" not in payload:
            raise ValueError("Missing required upstream field: timestamp")
        data = {k: v for k, v in payload.items() if k != "timestamp"}
        return cls(
            timestamp=float(payload["timestamp"]),
            data=data,
        )

    def to_dict(self) -> dict[str, Any]:
        result = dict(self.data)
        result["timestamp"] = self.timestamp
        return result

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_") or name in {"timestamp", "data"}:
            raise AttributeError(name)
        return self.data.get(name)


@dataclass
class SpeedMiddlewareConfig:
    name: str
    params: dict[str, Any]

    @classmethod
    def from_dict(cls, payload: Optional[dict[str, Any]]) -> Optional["SpeedMiddlewareConfig"]:
        if not payload:
            return None
        return cls(name=str(payload.get("name", "noop")), params=dict(payload.get("params", {})))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PilotDecision:
    path_action: Optional[str]
    speed_middleware: Optional[SpeedMiddlewareConfig]
    task_status: str
    environment_summary: str
    explain: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PilotDecision":
        return cls(
            path_action=payload.get("path_action"),
            speed_middleware=SpeedMiddlewareConfig.from_dict(payload.get("speed_middleware")),
            task_status=str(payload.get("task_status", "")),
            environment_summary=str(payload.get("environment_summary", "")),
            explain=str(payload.get("explain", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "path_action": self.path_action,
            "speed_middleware": (
                None if self.speed_middleware is None else self.speed_middleware.to_dict()
            ),
            "task_status": self.task_status,
            "environment_summary": self.environment_summary,
            "explain": self.explain,
        }

    def to_model_control(self, ego_speed_mps: float) -> dict[str, Any]:
        return {
            "path_action": self.path_action,
            "speed_middleware": (
                None if self.speed_middleware is None else self.speed_middleware.to_dict()
            ),
            "ego_speed_mps": float(ego_speed_mps),
            "task_status": self.task_status,
            "environment_summary": self.environment_summary,
        }
