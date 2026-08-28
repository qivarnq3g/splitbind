"""Normalized geometry used by attack and benchmark evidence."""

from __future__ import annotations

import math
from dataclasses import dataclass


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
