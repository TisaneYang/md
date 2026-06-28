from __future__ import annotations

import base64
from collections import deque
from typing import Any, Optional

from .types import PilotDecision, UpstreamCommand


class PilotContext:
    def __init__(
        self,
        window_size: int,
        save_images_in_context: bool = False,
        save_environment_summary: bool = True,
        image_jpeg_quality: int = 70,
    ) -> None:
        self.save_images_in_context = save_images_in_context
        self.save_environment_summary = save_environment_summary
        self.image_jpeg_quality = image_jpeg_quality
        self._items: deque[dict[str, Any]] = deque(maxlen=window_size)

    def snapshot(self) -> list[dict[str, Any]]:
        return list(self._items)

    def append(
        self,
        upstream: UpstreamCommand,
        decision: PilotDecision,
        vehicle_position: Optional[dict[str, Any]] = None,
        images: Optional[dict[str, Any]] = None,
    ) -> None:
        item: dict[str, Any] = {
            "upstream": upstream.to_dict(),
            "pilot_output": decision.to_dict(),
            "vehicle_position": vehicle_position or {},
        }

        if not self.save_environment_summary:
            item["pilot_output"].pop("environment_summary", None)

        if self.save_images_in_context and images:
            item["images"] = self._encode_images(images)

        self._items.append(item)

    def _encode_images(self, images: dict[str, Any]) -> dict[str, str]:
        try:
            import cv2
        except ImportError:
            return {}

        encoded: dict[str, str] = {}
        params = [int(cv2.IMWRITE_JPEG_QUALITY), int(self.image_jpeg_quality)]
        for name, image in images.items():
            ok, buffer = cv2.imencode(".jpg", image, params)
            if ok:
                encoded[name] = base64.b64encode(buffer.tobytes()).decode("ascii")
        return encoded
