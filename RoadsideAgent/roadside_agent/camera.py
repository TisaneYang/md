"""Roadside camera sensor management."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any, Dict, Optional

import numpy as np


@dataclass(frozen=True)
class RoadsideCameraSpec:
    """Absolute-world roadside camera configuration."""

    camera_id: str
    name: str
    x: float
    y: float
    z: float
    pitch: float
    yaw: float
    roll: float = 0.0
    width: int = 800
    height: int = 600
    fov: float = 90.0

    @property
    def intrinsics(self) -> Dict[str, float]:
        focal = self.width / (2.0 * np.tan(np.radians(self.fov) / 2.0))
        return {
            "fx": float(focal),
            "fy": float(focal),
            "cx": float(self.width) / 2.0,
            "cy": float(self.height) / 2.0,
        }


def carla_image_to_bgr(image: Any) -> np.ndarray:
    """Convert CARLA raw BGRA image data to OpenCV BGR."""
    array = np.frombuffer(image.raw_data, dtype=np.uint8)
    array = np.reshape(array, (image.height, image.width, 4))
    return array[:, :, :3].copy()


class RoadsideCameraSensor:
    """Spawn and buffer one world-fixed roadside RGB camera."""

    def __init__(self, world: Any, spec: RoadsideCameraSpec) -> None:
        self.world = world
        self.spec = spec
        self.sensor = None
        self._latest_frame = None
        self._latest_image = None
        self._lock = Lock()

    @property
    def transform(self) -> Any:
        if self.sensor is not None:
            return self.sensor.get_transform()
        return self._make_transform()

    def spawn(self) -> None:
        """Create the CARLA camera as an independent world actor."""
        if self.sensor is not None:
            return

        blueprint = self.world.get_blueprint_library().find("sensor.camera.rgb")
        blueprint.set_attribute("image_size_x", str(self.spec.width))
        blueprint.set_attribute("image_size_y", str(self.spec.height))
        blueprint.set_attribute("fov", str(self.spec.fov))
        blueprint.set_attribute("role_name", self.spec.camera_id)

        self.sensor = self.world.spawn_actor(blueprint, self._make_transform())
        self.sensor.listen(self._on_image)

    def get_latest_image(self) -> Optional[np.ndarray]:
        """Return the latest BGR image copied from the sensor callback."""
        with self._lock:
            if self._latest_image is None:
                return None
            return self._latest_image.copy()

    def get_latest_frame(self) -> Optional[int]:
        with self._lock:
            return self._latest_frame

    def destroy(self) -> None:
        if self.sensor is None:
            return
        self.sensor.stop()
        self.sensor.destroy()
        self.sensor = None

    def _on_image(self, image: Any) -> None:
        bgr = carla_image_to_bgr(image)
        with self._lock:
            self._latest_frame = getattr(image, "frame", None)
            self._latest_image = bgr

    def _make_transform(self) -> Any:
        import carla

        return carla.Transform(
            carla.Location(x=self.spec.x, y=self.spec.y, z=self.spec.z),
            carla.Rotation(
                pitch=self.spec.pitch,
                yaw=self.spec.yaw,
                roll=self.spec.roll,
            ),
        )
