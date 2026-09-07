from __future__ import annotations

import base64
import uuid

import cv2
import numpy as np


def marker_text(issuance_id: uuid.UUID) -> str:
    if not isinstance(issuance_id, uuid.UUID):
        raise TypeError("issuance_id must be a UUID")
    encoded = base64.b32encode(issuance_id.bytes).decode("ascii").rstrip("=")
    return f"SB1-{encoded[:20]}"


def apply_visible_marker(image: np.ndarray, issuance_id: uuid.UUID) -> np.ndarray:
    """Return a copy with a deterministic, high-contrast bottom-right marker."""
    if (
        not isinstance(image, np.ndarray)
        or image.dtype != np.uint8
        or image.ndim != 3
        or image.shape[2] not in (3, 4)
    ):
        raise ValueError("marker image must be an 8-bit BGR or BGRA raster")
    height, width = image.shape[:2]
    if height < 64 or width < 160:
        raise ValueError("marker image is too small")

    output = image.copy()
    text = marker_text(issuance_id)
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = max(0.42, min(1.1, width / 1100.0))
    thickness = max(1, round(scale * 2))
    (text_width, text_height), baseline = cv2.getTextSize(
        text, font, scale, thickness
    )
    inset = max(8, round(min(width, height) * 0.02))
    padding_x = max(6, round(scale * 8))
    padding_y = max(5, round(scale * 7))
    x = max(inset, width - inset - text_width - padding_x * 2)
    y_bottom = height - inset
    y_top = max(inset, y_bottom - text_height - baseline - padding_y * 2)
    cv2.rectangle(
        output,
        (x, y_top),
        (width - inset, y_bottom),
        (255, 255, 255, 255),
        thickness=cv2.FILLED,
    )
    cv2.rectangle(
        output,
        (x, y_top),
        (width - inset, y_bottom),
        (0, 0, 0, 255),
        thickness=max(1, thickness),
    )
    cv2.putText(
        output,
        text,
        (x + padding_x, y_bottom - baseline - padding_y),
        font,
        scale,
        (0, 0, 0, 255),
        thickness,
        cv2.LINE_AA,
    )
    return output
