from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .communication import SendResult, VehicleCommandClient
from .config import RoadsideRuntimeConfig
from .context import RoadsideContext
from .cloud_vlm_client import build_cloud_vlm_client
from .logger import RoadsideLogger
from .types import (
    RoadsideBatchInput,
    RoadsideDecision,
    RoadsideImageReference,
    RoadsideVehicleObservation,
)
from .vehicle_registry import VehicleRegistry


class RoadsideRuntime:
    def __init__(
        self,
        config: RoadsideRuntimeConfig,
        command_client: Optional[VehicleCommandClient] = None,
    ) -> None:
        self.config = config
        self.enabled = bool(config.enabled)
        self.command_client = command_client or VehicleCommandClient()
        self.cloud_client = build_cloud_vlm_client(config.cloud)
        self.context = RoadsideContext(window_size=config.context.window_size)
        self.logger = RoadsideLogger(config.logging.path, config.logging.enabled)
        self.last_decision: Optional[RoadsideDecision] = None
        self.last_error: Optional[str] = None

    @classmethod
    def from_config_path(
        cls,
        path: Optional[str | Path],
        command_client: Optional[VehicleCommandClient] = None,
    ) -> "RoadsideRuntime":
        return cls(
            config=RoadsideRuntimeConfig.from_path(path),
            command_client=command_client,
        )

    def step(
        self,
        tick: int,
        timestamp: float,
        route_name: str,
        scene_description: str,
        perception: dict[str, Any],
        vehicle_registry: VehicleRegistry,
        admin_instruction: Optional[dict[str, Any]] = None,
    ) -> Optional[RoadsideDecision]:
        self.last_error = None
        if not self.enabled:
            return None

        self._sync_endpoints(vehicle_registry)
        batch_input, images = self._build_batch_input(
            route_name=route_name,
            tick=tick,
            timestamp=timestamp,
            scene_description=scene_description,
            perception=perception,
            vehicle_registry=vehicle_registry,
            admin_instruction=admin_instruction,
        )
        if not batch_input.vehicles:
            return self.last_decision

        try:
            decision = self.cloud_client.decide(batch_input=batch_input, images=images)
        except Exception as exc:
            self.last_error = str(exc)
            self.logger.log_tick(
                tick=tick,
                timestamp=timestamp,
                batch_input=batch_input,
                decision=None,
                fallback_reason=self.last_error,
            )
            return self.last_decision

        send_results = self._send_vehicle_outputs(decision)
        self.last_decision = decision
        self.context.append(
            tick=tick,
            timestamp=timestamp,
            decision=decision,
            send_results=send_results,
        )
        self.logger.log_tick(
            tick=tick,
            timestamp=timestamp,
            batch_input=batch_input,
            decision=decision,
            send_results=send_results,
        )
        return decision

    def _sync_endpoints(self, vehicle_registry: VehicleRegistry) -> None:
        for vehicle_id, endpoint in vehicle_registry.endpoint_map().items():
            self.command_client.register_endpoint(vehicle_id, endpoint)

    def _build_batch_input(
        self,
        route_name: str,
        tick: int,
        timestamp: float,
        scene_description: str,
        perception: dict[str, Any],
        vehicle_registry: VehicleRegistry,
        admin_instruction: Optional[dict[str, Any]] = None,
    ) -> tuple[RoadsideBatchInput, list[dict[str, Any]]]:
        vehicles_payload = perception.get("vehicles", {})
        observations: list[RoadsideVehicleObservation] = []
        images: list[dict[str, Any]] = []

        for vehicle_id in sorted(vehicles_payload.keys(), key=str):
            vehicle_payload = vehicles_payload[vehicle_id]
            record = vehicle_registry.get(vehicle_id)
            state = {} if record is None else dict(record.state)
            visible_cameras = sorted(vehicle_payload.get("visible_cameras", []), key=str)
            camera_outputs = vehicle_payload.get("cameras", {})
            image_refs: list[RoadsideImageReference] = []
            for camera_id in visible_cameras:
                camera_output = camera_outputs.get(camera_id)
                if camera_output is None:
                    continue
                image_key = f"vehicle_{vehicle_id}_camera_{camera_id}"
                image_refs.append(
                    RoadsideImageReference(
                        image_key=image_key,
                        camera_id=camera_id,
                        camera_name=camera_output.camera_name,
                    )
                )
                images.append(
                    {
                        "vehicle_id": str(vehicle_id),
                        "camera_id": str(camera_id),
                        "image_key": image_key,
                        "image": camera_output.image_with_bbox,
                    }
                )

            observations.append(
                RoadsideVehicleObservation(
                    vehicle_id=str(vehicle_id),
                    state=state,
                    visible_cameras=visible_cameras,
                    in_blind_spot=bool(vehicle_payload.get("in_blind_spot", False)),
                    images=image_refs,
                )
            )

        global_context: dict[str, Any] = {
            "history": self.context.snapshot(),
        }
        if admin_instruction and admin_instruction.get("has_instruction"):
            global_context["admin_instruction"] = admin_instruction

        batch_input = RoadsideBatchInput(
            route_name=str(route_name),
            tick=int(tick),
            timestamp=float(timestamp),
            global_context=global_context,
            vehicles=observations,
            scene_description=str(scene_description or ""),
        )
        return batch_input, images

    def _send_vehicle_outputs(self, decision: RoadsideDecision) -> list[dict[str, Any]]:
        send_results: list[dict[str, Any]] = []
        for item in decision.vehicle_outputs:
            if not item.should_send or not item.message:
                continue
            result = self.command_client.send_message(item.vehicle_id, item.message)
            send_results.append(self._send_result_to_dict(result))
        return send_results

    @staticmethod
    def _send_result_to_dict(result: SendResult) -> dict[str, Any]:
        return {
            "vehicle_id": result.vehicle_id,
            "endpoint": result.endpoint.address,
            "ok": result.ok,
            "status_code": result.status_code,
            "response_body": result.response_body,
            "error": result.error,
        }
