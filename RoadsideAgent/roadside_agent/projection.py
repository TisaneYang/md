"""Projection utilities for roadside cameras.

The math intentionally follows the old RoadsideAgent convention:
CARLA camera coordinates use X as forward, Y as right, Z as up, then are
converted to pinhole camera coordinates before applying intrinsics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional, Tuple

import numpy as np


@dataclass(frozen=True)
class ProjectionResult:
    """2D projection output for one target actor in one roadside camera."""

    bbox: Optional[Tuple[int, int, int, int]]
    corners_2d: np.ndarray
    visible: bool
    clipped_by_near_plane: bool
    reason: str = ""


def _location_xyz(location: Any) -> Tuple[float, float, float]:
    if isinstance(location, dict):
        return float(location["x"]), float(location["y"]), float(location["z"])
    return float(location.x), float(location.y), float(location.z)


def _rotation_dict(rotation: Any) -> Dict[str, float]:
    if isinstance(rotation, dict):
        return {
            "pitch": float(rotation["pitch"]),
            "yaw": float(rotation["yaw"]),
            "roll": float(rotation["roll"]),
        }
    return {
        "pitch": float(rotation.pitch),
        "yaw": float(rotation.yaw),
        "roll": float(rotation.roll),
    }


def _transform_location(transform: Any) -> Any:
    if isinstance(transform, dict):
        return transform["location"]
    return transform.location


def _transform_rotation(transform: Any) -> Any:
    if isinstance(transform, dict):
        return transform["rotation"]
    return transform.rotation


def _transform_matrix(transform: Any) -> np.ndarray:
    """Return a 4x4 local-to-world transform matrix."""
    if hasattr(transform, "get_matrix"):
        return np.asarray(transform.get_matrix(), dtype=float)

    location = _transform_location(transform)
    rotation = _transform_rotation(transform)
    x, y, z = _location_xyz(location)
    matrix = np.eye(4, dtype=float)
    matrix[:3, :3] = euler_to_rotation_matrix(_rotation_dict(rotation))
    matrix[:3, 3] = np.array([x, y, z], dtype=float)
    return matrix


def euler_to_rotation_matrix(rotation: Dict[str, float]) -> np.ndarray:
    """Convert CARLA/UE4 pitch-yaw-roll degrees to a rotation matrix.

    This mirrors the old implementation to keep the projection behavior close
    to the version that was already validated in scenarios.
    """
    pitch = np.radians(-rotation["pitch"])
    yaw = np.radians(rotation["yaw"])
    roll = np.radians(-rotation["roll"])

    rz = np.array(
        [
            [np.cos(yaw), -np.sin(yaw), 0.0],
            [np.sin(yaw), np.cos(yaw), 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    ry = np.array(
        [
            [np.cos(pitch), 0.0, np.sin(pitch)],
            [0.0, 1.0, 0.0],
            [-np.sin(pitch), 0.0, np.cos(pitch)],
        ]
    )
    rx = np.array(
        [
            [1.0, 0.0, 0.0],
            [0.0, np.cos(roll), -np.sin(roll)],
            [0.0, np.sin(roll), np.cos(roll)],
        ]
    )
    return rz @ ry @ rx


class RoadsideProjector:
    """Project a CARLA vehicle actor to a roadside camera image."""

    def __init__(
        self,
        camera_intrinsics: Dict[str, float],
        near_clip: float = 0.10,
        min_visible_corners: int = 2,
    ) -> None:
        self.fx = float(camera_intrinsics["fx"])
        self.fy = float(camera_intrinsics["fy"])
        self.cx = float(camera_intrinsics["cx"])
        self.cy = float(camera_intrinsics["cy"])
        self.near_clip = float(near_clip)
        self.min_visible_corners = int(min_visible_corners)

    @staticmethod
    def get_actor_bbox_corners_world(actor: Any) -> np.ndarray:
        """Return the target actor bounding-box corners in world coordinates.

        Mirrors the old RoadsideAgent convention: the actor transform location
        is used directly as the bbox center, and extent is half size.
        """
        bbox = actor.bounding_box
        extent = bbox.extent

        ex, ey, ez = float(extent.x), float(extent.y), float(extent.z)
        corners_local = np.array(
            [
                [ex, ey, -ez],
                [ex, -ey, -ez],
                [-ex, -ey, -ez],
                [-ex, ey, -ez],
                [ex, ey, ez],
                [ex, -ey, ez],
                [-ex, -ey, ez],
                [-ex, ey, ez],
            ],
            dtype=float,
        )

        transform = actor.get_transform()
        matrix = _transform_matrix(transform)
        homogeneous = np.column_stack([corners_local, np.ones(len(corners_local))])
        corners_world = (matrix @ homogeneous.T).T[:, :3]
        return corners_world

    @staticmethod
    def world_to_camera(
        points_world: np.ndarray,
        camera_transform: Any,
    ) -> np.ndarray:
        """Transform world-space points into the CARLA camera frame."""
        camera_location = _transform_location(camera_transform)
        camera_rotation = _transform_rotation(camera_transform)
        camera_pos = np.array(_location_xyz(camera_location), dtype=float)
        rotation = euler_to_rotation_matrix(_rotation_dict(camera_rotation))
        points_translated = points_world - camera_pos
        return (rotation.T @ points_translated.T).T

    def project_to_image(self, points_camera: np.ndarray) -> np.ndarray:
        """Project camera-frame points to pixel coordinates."""
        x_standard = points_camera[:, 1]
        y_standard = -points_camera[:, 2]
        z_standard = points_camera[:, 0]

        u = self.fx * (x_standard / z_standard) + self.cx
        v = self.fy * (y_standard / z_standard) + self.cy
        return np.column_stack([u, v])

    def project_actor(
        self,
        actor: Any,
        camera_transform: Any,
        image_width: int,
        image_height: int,
    ) -> ProjectionResult:
        """Project a target actor and return one clipped green-box bbox."""
        corners_world = self.get_actor_bbox_corners_world(actor)
        corners_camera = self.world_to_camera(corners_world, camera_transform)

        depth = corners_camera[:, 0]
        valid_mask = depth > self.near_clip
        clipped_by_near_plane = bool(np.any(~valid_mask))
        if int(np.sum(valid_mask)) < self.min_visible_corners:
            return ProjectionResult(
                bbox=None,
                corners_2d=np.empty((0, 2), dtype=float),
                visible=False,
                clipped_by_near_plane=clipped_by_near_plane,
                reason="target is behind or too close to the camera near plane",
            )

        corners_2d = self.project_to_image(corners_camera[valid_mask])
        bbox = self._bbox_from_points(corners_2d, image_width, image_height)
        if bbox is None:
            return ProjectionResult(
                bbox=None,
                corners_2d=corners_2d,
                visible=False,
                clipped_by_near_plane=clipped_by_near_plane,
                reason="projected bbox does not intersect the image",
            )

        return ProjectionResult(
            bbox=bbox,
            corners_2d=corners_2d,
            visible=True,
            clipped_by_near_plane=clipped_by_near_plane,
        )

    @staticmethod
    def _bbox_from_points(
        points_2d: np.ndarray,
        image_width: int,
        image_height: int,
    ) -> Optional[Tuple[int, int, int, int]]:
        if points_2d.size == 0:
            return None

        x_min = int(np.floor(np.min(points_2d[:, 0])))
        y_min = int(np.floor(np.min(points_2d[:, 1])))
        x_max = int(np.ceil(np.max(points_2d[:, 0])))
        y_max = int(np.ceil(np.max(points_2d[:, 1])))

        if x_max < 0 or y_max < 0 or x_min >= image_width or y_min >= image_height:
            return None

        x_min = max(0, min(x_min, image_width - 1))
        y_min = max(0, min(y_min, image_height - 1))
        x_max = max(0, min(x_max, image_width - 1))
        y_max = max(0, min(y_max, image_height - 1))

        if x_max <= x_min or y_max <= y_min:
            return None
        return x_min, y_min, x_max, y_max
