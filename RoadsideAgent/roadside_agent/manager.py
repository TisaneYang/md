"""High-level roadside perception orchestration.

The agent decision layer is intentionally left blank for now. This manager only
owns roadside camera capture, target actor projection, and bbox visualization.
"""

from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

import cv2
import yaml

from .camera import RoadsideCameraSensor, RoadsideCameraSpec
from .communication import SendResult, VehicleCommandClient
from .projection import ProjectionResult, RoadsideProjector
from .visualization import draw_target_bbox


@dataclass
class CameraPerception:
    """Per-camera output for the target vehicle."""

    camera_id: str
    camera_name: str
    image_with_bbox: Any
    projection: ProjectionResult
    frame: Optional[int]


class RoadsidePerceptionManager:
    """Manage roadside cameras and target-vehicle bbox projection."""

    def __init__(
        self,
        world: Any,
        camera_specs: Iterable[RoadsideCameraSpec],
        near_clip: float = 0.10,
        bbox_thickness: int = 4,
        sample_interval_ticks: int = 10,
        scene_description: str = "",
        scene_name: str = "default_scene",
        output_root: Optional[str | Path] = None,
    ) -> None:
        self.world = world
        self.near_clip = near_clip
        self.bbox_thickness = bbox_thickness
        self.sample_interval_ticks = max(1, int(sample_interval_ticks))
        self.scene_description = str(scene_description or "")
        self.scene_name = str(scene_name or "default_scene")
        self.cameras: List[RoadsideCameraSensor] = [
            RoadsideCameraSensor(world, spec) for spec in camera_specs
        ]
        self.projectors: Dict[str, RoadsideProjector] = {
            camera.spec.camera_id: RoadsideProjector(
                camera.spec.intrinsics,
                near_clip=near_clip,
            )
            for camera in self.cameras
        }
        self.output_root = (
            Path(output_root)
            if output_root is not None
            else Path(__file__).resolve().parents[1] / "output"
        )
        self.run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.run_output_dir = self.output_root / self.scene_name / self.run_timestamp
        self.camera_output_dirs: Dict[str, Path] = {
            camera.spec.camera_id: self.run_output_dir / camera.spec.camera_id
            for camera in self.cameras
        }
        for directory in self.camera_output_dirs.values():
            directory.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_config(cls, world: Any, config_path: str | Path) -> "RoadsidePerceptionManager":
        """Build a manager from a YAML config file."""
        resolved_config_path = Path(config_path)
        with open(resolved_config_path, "r", encoding="utf-8") as file:
            config = yaml.safe_load(file) or {}

        camera_specs = [
            RoadsideCameraSpec(
                camera_id=str(item["id"]),
                name=str(item.get("name", item["id"])),
                x=float(item["location"]["x"]),
                y=float(item["location"]["y"]),
                z=float(item["location"]["z"]),
                pitch=float(item["rotation"]["pitch"]),
                yaw=float(item["rotation"]["yaw"]),
                roll=float(item["rotation"].get("roll", 0.0)),
                width=int(item.get("image_size", {}).get("width", 800)),
                height=int(item.get("image_size", {}).get("height", 600)),
                fov=float(item.get("fov", 90.0)),
            )
            for item in config.get("cameras", [])
            if item.get("enabled", True)
        ]
        return cls(
            world=world,
            camera_specs=camera_specs,
            near_clip=float(config.get("projection", {}).get("near_clip", 0.10)),
            bbox_thickness=int(config.get("visualization", {}).get("bbox_thickness", 4)),
            sample_interval_ticks=int(config.get("sampling", {}).get("interval_ticks", 10)),
            scene_description=str(config.get("scene_description", "") or ""),
            scene_name=str(config.get("route_name") or resolved_config_path.stem),
        )

    @classmethod
    def from_route_config(
        cls,
        world: Any,
        route_name: str,
        config_root: str | Path,
    ) -> "RoadsidePerceptionManager":
        """Build a manager from a preconfigured route-level camera file.

        Bench2Drive leaderboard configs are named like ``RouteScenario_{route_id}``.
        The expected file path is ``{config_root}/routes/{route_name}.yaml``.
        """
        resolved_route_name = str(route_name)
        if not resolved_route_name.startswith("RouteScenario_"):
            resolved_route_name = f"RouteScenario_{resolved_route_name}"
        config_path = Path(config_root) / "routes" / f"{resolved_route_name}.yaml"
        if not config_path.exists():
            raise FileNotFoundError(f"roadside camera config not found: {config_path}")
        return cls.from_config(world, config_path)

    def spawn_cameras(self, warmup_ticks: int = 2) -> None:
        """Spawn all roadside cameras as world-fixed sensors."""
        for camera in self.cameras:
            camera.spawn()

        for _ in range(max(0, warmup_ticks)):
            if self.world.get_settings().synchronous_mode:
                self.world.tick()
            else:
                self.world.wait_for_tick()

    def should_sample(self, tick_index: int) -> bool:
        """Return whether RoadsideAgent should run on this simulation tick."""
        return int(tick_index) % self.sample_interval_ticks == 0

    def perceive_target(
        self,
        target_actor: Any,
        vehicle_id: Optional[str] = None,
        sample_index: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Capture latest roadside images and draw the target vehicle bbox."""
        outputs: Dict[str, CameraPerception] = {}
        visible_cameras = []
        resolved_vehicle_id = str(vehicle_id if vehicle_id is not None else target_actor.id)
        label = f"vehicle {resolved_vehicle_id}"

        for camera in self.cameras:
            raw_image = camera.get_latest_image()
            if raw_image is None:
                continue

            projector = self.projectors[camera.spec.camera_id]
            projection = projector.project_actor(
                actor=target_actor,
                camera_transform=camera.transform,
                image_width=camera.spec.width,
                image_height=camera.spec.height,
            )
            if projection.visible:
                visible_cameras.append(camera.spec.camera_id)

            image_with_bbox = draw_target_bbox(
                raw_image,
                projection.bbox,
                label=label if projection.visible else None,
                thickness=self.bbox_thickness,
            )
            outputs[camera.spec.camera_id] = CameraPerception(
                camera_id=camera.spec.camera_id,
                camera_name=camera.spec.name,
                image_with_bbox=image_with_bbox,
                projection=projection,
                frame=camera.get_latest_frame(),
            )
            self._save_camera_image(
                camera_id=camera.spec.camera_id,
                vehicle_id=resolved_vehicle_id,
                frame=outputs[camera.spec.camera_id].frame,
                image=image_with_bbox,
                visible=projection.visible,
                sample_index=sample_index,
            )

        return {
            "vehicle_id": resolved_vehicle_id,
            "visible_cameras": visible_cameras,
            "in_blind_spot": len(visible_cameras) == 0,
            "cameras": outputs,
        }

    def perceive_targets(
        self,
        target_actors: Mapping[str, Any],
        sample_index: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Perceive multiple vehicles in a batch without defining policy logic.

        The output is keyed by caller-provided vehicle id. Whether future Agent
        prompts should use one shared image with many labeled boxes or one image
        per vehicle is intentionally left to the Agent design.
        """
        return {
            "vehicles": {
                str(vehicle_id): self.perceive_target(
                    actor,
                    vehicle_id=str(vehicle_id),
                    sample_index=sample_index,
                )
                for vehicle_id, actor in target_actors.items()
            }
        }

    def destroy(self) -> None:
        for camera in self.cameras:
            camera.destroy()

    def _save_camera_image(
        self,
        camera_id: str,
        vehicle_id: str,
        frame: Optional[int],
        image: Any,
        visible: bool,
        sample_index: Optional[int] = None,
    ) -> None:
        if image is None:
            return

        camera_dir = self.camera_output_dirs[camera_id]
        frame_text = "unknown" if frame is None else f"{int(frame):06d}"
        parts = [f"frame_{frame_text}", f"vehicle_{vehicle_id}"]
        if sample_index is not None:
            parts.insert(0, f"tick_{int(sample_index):06d}")
        parts.append("visible" if visible else "not_visible")
        output_path = camera_dir / ("_".join(parts) + ".jpg")
        cv2.imwrite(str(output_path), image)


class RoadsideAgent:
    """Placeholder for the future policy/LLM layer."""

    def __init__(
        self,
        perception_manager: RoadsidePerceptionManager,
        command_client: Optional[VehicleCommandClient] = None,
    ) -> None:
        self.perception_manager = perception_manager
        self.command_client = command_client or VehicleCommandClient()

    def analyze(
        self,
        target_actor: Any = None,
        target_actors: Optional[Mapping[str, Any]] = None,
        sample_index: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Return perception output only until business logic is defined."""
        if target_actors is not None:
            perception = self.perception_manager.perceive_targets(
                target_actors,
                sample_index=sample_index,
            )
        elif target_actor is not None:
            perception = self.perception_manager.perceive_target(
                target_actor,
                sample_index=sample_index,
            )
        else:
            raise ValueError("target_actor or target_actors must be provided")

        return {
            "perception": perception,
            "agent_result": None,
        }

    def send_to_vehicle(self, vehicle_id: str, message: Mapping[str, Any] | str) -> SendResult:
        """Send a roadside command to one vehicle by id."""
        return self.command_client.send_message(vehicle_id, message)
