"""Normalized geometry used by attack and benchmark evidence."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable


Transform = tuple[float, float, float, float, float, float, float, float, float]
IDENTITY_TRANSFORM: Transform = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)


@dataclass(frozen=True, slots=True)
class NormalizedRect:
    """An axis-aligned rectangle in the closed unit image coordinate space."""

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        values = (self.x, self.y, self.width, self.height)
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
            raise TypeError("normalized rectangle values must be real numbers")
        if not all(math.isfinite(float(value)) for value in values):
            raise ValueError("normalized rectangle values must be finite")
        if self.x < 0.0 or self.y < 0.0 or self.width <= 0.0 or self.height <= 0.0:
            raise ValueError("normalized rectangle must be non-empty and start within [0, 1]")
        if self.x + self.width > 1.0 or self.y + self.height > 1.0:
            raise ValueError("normalized rectangle must fit within [0, 1]")

    @property
    def right(self) -> float:
        return float(self.x + self.width)

    @property
    def bottom(self) -> float:
        return float(self.y + self.height)

    def as_dict(self) -> dict[str, float]:
        return {
            "x": float(self.x),
            "y": float(self.y),
            "width": float(self.width),
            "height": float(self.height),
        }


def compose_transforms(after: Transform, before: Transform) -> Transform:
    """Compose normalized homographies so ``before`` is applied first."""

    left = _validated_transform(after)
    right = _validated_transform(before)
    return tuple(
        sum(left[row * 3 + inner] * right[inner * 3 + column] for inner in range(3))
        for row in range(3)
        for column in range(3)
    )  # type: ignore[return-value]


def transform_regions(
    regions: Iterable[NormalizedRect], transform: Transform
) -> tuple[NormalizedRect, ...]:
    """Map rectangles to clipped axis-aligned envelopes in output coordinates."""

    matrix = _validated_transform(transform)
    if matrix == IDENTITY_TRANSFORM:
        return tuple(regions)
    mapped: list[NormalizedRect] = []
    for region in regions:
        if not isinstance(region, NormalizedRect):
            raise TypeError("regions must contain NormalizedRect values")
        points = (
            _transform_point(region.x, region.y, matrix),
            _transform_point(region.right, region.y, matrix),
            _transform_point(region.right, region.bottom, matrix),
            _transform_point(region.x, region.bottom, matrix),
        )
        left = max(0.0, min(point[0] for point in points))
        top = max(0.0, min(point[1] for point in points))
        right = min(1.0, max(point[0] for point in points))
        bottom = min(1.0, max(point[1] for point in points))
        if right > left and bottom > top:
            mapped.append(NormalizedRect(left, top, right - left, bottom - top))
    return tuple(mapped)


def merge_regions(*groups: Iterable[NormalizedRect]) -> tuple[NormalizedRect, ...]:
    """Merge normalized regions in stable order without duplicate rectangles."""

    merged: list[NormalizedRect] = []
    seen: set[NormalizedRect] = set()
    for group in groups:
        for region in group:
            if not isinstance(region, NormalizedRect):
                raise TypeError("regions must contain NormalizedRect values")
            if region not in seen:
                merged.append(region)
                seen.add(region)
    return tuple(merged)


def _transform_point(x: float, y: float, matrix: Transform) -> tuple[float, float]:
    denominator = matrix[6] * x + matrix[7] * y + matrix[8]
    if not math.isfinite(denominator) or abs(denominator) <= 1e-15:
        raise ValueError("ground-truth transform maps a corner to infinity")
    mapped_x = (matrix[0] * x + matrix[1] * y + matrix[2]) / denominator
    mapped_y = (matrix[3] * x + matrix[4] * y + matrix[5]) / denominator
    if not math.isfinite(mapped_x) or not math.isfinite(mapped_y):
        raise ValueError("ground-truth transform produced non-finite coordinates")
    return mapped_x, mapped_y


def _validated_transform(transform: Transform) -> Transform:
    if not isinstance(transform, tuple) or len(transform) != 9:
        raise TypeError("transform must be a 9-value tuple")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        for value in transform
    ):
        raise ValueError("transform values must be finite real numbers")
    return tuple(float(value) for value in transform)  # type: ignore[return-value]
