from __future__ import annotations

from typing import Any, Optional


# Engineering reference values used only for post-inference filtering.
# They are not treated as official MindDrive physical speed definitions.
SPEED_REFERENCE_MPS = {
    "<stop>": 0.0,
    "<slow_down>": 1.0,
    "<maintain_slow_speed>": 2.0,
    "<maintain_moderate_speed>": 3.0,
    "<maintain_fast_speed>": 4.0,
    "<speed_up>": 5.0,
    "<slow_down_rapidly>": -1.0,
}

SPEED_ORDER = [
    "<stop>",
    "<slow_down>",
    "<maintain_slow_speed>",
    "<maintain_moderate_speed>",
    "<maintain_fast_speed>",
    "<speed_up>",
]


class SpeedMiddleware:
    def map(self, raw_speed_command: str, ego_speed_mps: Optional[float] = None) -> str:
        return raw_speed_command


class NoopSpeedMiddleware(SpeedMiddleware):
    pass


class CapSpeedMiddleware(SpeedMiddleware):
    def __init__(self, max_speed_mps: float) -> None:
        self.max_speed_mps = max_speed_mps

    def map(self, raw_speed_command: str, ego_speed_mps: Optional[float] = None) -> str:
        raw_ref = SPEED_REFERENCE_MPS.get(raw_speed_command)
        if raw_ref is None or raw_ref <= self.max_speed_mps:
            return raw_speed_command

        allowed = [
            command
            for command in SPEED_ORDER
            if SPEED_REFERENCE_MPS[command] <= self.max_speed_mps
        ]
        return allowed[-1] if allowed else "<stop>"


class DecelerateIfOverspeedMiddleware(SpeedMiddleware):
    def __init__(self, target_speed_mps: float, tolerance_mps: float = 0.3) -> None:
        self.target_speed_mps = target_speed_mps
        self.tolerance_mps = tolerance_mps

    def map(self, raw_speed_command: str, ego_speed_mps: Optional[float] = None) -> str:
        if ego_speed_mps is None:
            return raw_speed_command

        if ego_speed_mps > self.target_speed_mps + self.tolerance_mps:
            return "<slow_down>"

        return CapSpeedMiddleware(self.target_speed_mps).map(raw_speed_command, ego_speed_mps)


def build_speed_middleware(config: Optional[dict[str, Any]]) -> SpeedMiddleware:
    if not config:
        return NoopSpeedMiddleware()

    name = str(config.get("name", "noop"))
    params = dict(config.get("params", {}))

    if name == "cap_speed":
        return CapSpeedMiddleware(max_speed_mps=float(params["max_speed_mps"]))

    if name == "decelerate_if_overspeed":
        return DecelerateIfOverspeedMiddleware(
            target_speed_mps=float(params["target_speed_mps"]),
            tolerance_mps=float(params.get("tolerance_mps", 0.3)),
        )

    return NoopSpeedMiddleware()

