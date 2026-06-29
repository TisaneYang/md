from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class RoadsideImageReference:
    image_key: str
    camera_id: str
    camera_name: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_key": self.image_key,
            "camera_id": self.camera_id,
            "camera_name": self.camera_name,
        }


@dataclass
class RoadsideVehicleObservation:
    vehicle_id: str
    state: dict[str, Any]
    visible_cameras: list[str]
    in_blind_spot: bool
    images: list[RoadsideImageReference] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "vehicle_id": self.vehicle_id,
            "state": self.state,
            "visible_cameras": list(self.visible_cameras),
            "in_blind_spot": self.in_blind_spot,
            "images": [item.to_dict() for item in self.images],
        }


@dataclass
class RoadsideBatchInput:
    route_name: str
    tick: int
    timestamp: float
    global_context: dict[str, Any]
    vehicles: list[RoadsideVehicleObservation]
    scene_description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "route_name": self.route_name,
            "tick": self.tick,
            "timestamp": self.timestamp,
            "global_context": self.global_context,
            "vehicles": [vehicle.to_dict() for vehicle in self.vehicles],
            "required_output": {
                "global_summary": "string",
                "vehicle_outputs": [
                    {
                        "vehicle_id": "string",
                        "should_send": "bool",
                        "message": "string|null",
                    }
                ],
            },
        }


@dataclass
class RoadsideVehicleOutput:
    vehicle_id: str
    should_send: bool
    message: Optional[str] = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RoadsideVehicleOutput":
        message = payload.get("message")
        if message is not None:
            message = str(message)
        raw_should_send = payload.get("should_send", False)
        if isinstance(raw_should_send, bool):
            should_send = raw_should_send
        elif isinstance(raw_should_send, str):
            should_send = raw_should_send.strip().lower() in {"true", "1", "yes", "y"}
        else:
            should_send = bool(raw_should_send)
        return cls(
            vehicle_id=str(payload.get("vehicle_id", "")),
            should_send=should_send,
            message=message,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "vehicle_id": self.vehicle_id,
            "should_send": self.should_send,
            "message": self.message,
        }


@dataclass
class RoadsideDecision:
    global_summary: str
    vehicle_outputs: list[RoadsideVehicleOutput] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RoadsideDecision":
        outputs = payload.get("vehicle_outputs", [])
        if not isinstance(outputs, list):
            outputs = []
        return cls(
            global_summary=str(payload.get("global_summary", "")),
            vehicle_outputs=[
                RoadsideVehicleOutput.from_dict(item)
                for item in outputs
                if isinstance(item, dict)
            ],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "global_summary": self.global_summary,
            "vehicle_outputs": [item.to_dict() for item in self.vehicle_outputs],
        }
