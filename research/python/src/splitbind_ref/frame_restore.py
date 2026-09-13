from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray


MIN_CONTENT_FRACTION = 0.20
DEFAULT_BORDER_TOLERANCE = 6


@dataclass(frozen=True, slots=True)
class RestoredFrame:
    image: NDArray[np.uint8]
    source_to_canonical: NDArray[np.float64]
    top: int
    left: int
    height: int
    width: int
    trimmed: bool


def content_bounds(
    page: NDArray[np.uint8],
    *,
    tolerance: int = DEFAULT_BORDER_TOLERANCE,
) -> tuple[int, int, int, int]:
    """Return top, left, height, width of the page inside a uniform border."""

    if page.ndim == 3:
        grey = cv2.cvtColor(page, cv2.COLOR_BGR2GRAY)
    else:
        grey = page
    height, width = grey.shape[:2]
    if height == 0 or width == 0:
        return 0, 0, height, width

    corners = np.array(
        [grey[0, 0], grey[0, -1], grey[-1, 0], grey[-1, -1]], dtype=np.int16
    )
    if int(corners.max()) - int(corners.min()) > tolerance:
        return 0, 0, height, width
    border = int(np.median(corners))

    differs = np.abs(grey.astype(np.int16) - border) > tolerance
    rows = np.flatnonzero(differs.any(axis=1))
    columns = np.flatnonzero(differs.any(axis=0))
    if rows.size == 0 or columns.size == 0:
        return 0, 0, height, width

    top = int(rows[0])
    bottom = int(rows[-1]) + 1
    left = int(columns[0])
    right = int(columns[-1]) + 1
    content_height = bottom - top
    content_width = right - left
    if (
        content_height < MIN_CONTENT_FRACTION * height
        or content_width < MIN_CONTENT_FRACTION * width
    ):
        return 0, 0, height, width
    return top, left, content_height, content_width


def restore_frame(
    page: NDArray[np.uint8],
    canonical_shape: tuple[int, int],
    *,
    interpolation: int = cv2.INTER_AREA,
    tolerance: int = DEFAULT_BORDER_TOLERANCE,
) -> RestoredFrame | None:
    """Trim a uniform border, then map the remaining page onto the canonical canvas.

    Returns None when the page already fills the canonical canvas exactly, so the
    caller keeps its existing identity hypothesis instead of a duplicate.
    """

    canonical_height, canonical_width = canonical_shape
    if canonical_height <= 0 or canonical_width <= 0:
        return None
    top, left, height, width = content_bounds(page, tolerance=tolerance)
    if height <= 0 or width <= 0:
        return None

    source_height, source_width = page.shape[:2]
    trimmed = (top, left, height, width) != (0, 0, source_height, source_width)
    if not trimmed and (source_height, source_width) == canonical_shape:
        return None

    content = page[top : top + height, left : left + width]
    restored = cv2.resize(
        content,
        (canonical_width, canonical_height),
        interpolation=interpolation,
    )
    scale_y = canonical_height / height
    scale_x = canonical_width / width
    matrix = np.array(
        [
            [scale_x, 0.0, -left * scale_x + (scale_x - 1.0) / 2.0],
            [0.0, scale_y, -top * scale_y + (scale_y - 1.0) / 2.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    return RestoredFrame(
        image=np.ascontiguousarray(restored, dtype=np.uint8),
        source_to_canonical=matrix,
        top=top,
        left=left,
        height=height,
        width=width,
        trimmed=trimmed,
    )
