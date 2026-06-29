"""Image drawing helpers for RoadsideAgent."""

from __future__ import annotations

from typing import Optional, Tuple

import cv2
import numpy as np


GREEN_BGR = (0, 255, 0)


def draw_target_bbox(
    image: np.ndarray,
    bbox: Optional[Tuple[int, int, int, int]],
    label: Optional[str] = None,
    color: Tuple[int, int, int] = GREEN_BGR,
    thickness: int = 4,
) -> np.ndarray:
    """Draw one 2D target vehicle bbox on a BGR image."""
    output = image.copy()
    if bbox is None:
        return output

    x_min, y_min, x_max, y_max = bbox
    cv2.rectangle(output, (x_min, y_min), (x_max, y_max), color, thickness)

    if label:
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.6
        text_thickness = 2
        padding = 4
        text_size, baseline = cv2.getTextSize(label, font, font_scale, text_thickness)
        text_width, text_height = text_size

        label_x = x_min
        label_y = max(0, y_min - text_height - baseline - 2 * padding)
        if label_y == 0:
            label_y = min(output.shape[0] - text_height - baseline - 2 * padding, y_min + thickness)

        cv2.rectangle(
            output,
            (label_x, label_y),
            (label_x + text_width + 2 * padding, label_y + text_height + baseline + 2 * padding),
            color,
            -1,
        )
        cv2.putText(
            output,
            label,
            (label_x + padding, label_y + padding + text_height),
            font,
            font_scale,
            (0, 0, 0),
            text_thickness,
            cv2.LINE_AA,
        )
    return output
