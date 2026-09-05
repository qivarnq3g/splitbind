"""Bounded shape-prior geometry hypotheses for fingerprint V3."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np
from numpy.typing import NDArray

from .fingerprint_v3_profile import FingerprintV3Profile, v2_pilot_profile
from .synchronization import SyncTemplate
from .synchronization_v2 import align_page_v2


_MAX_PAGE_PIXELS = 40_000_000
_MATRIX_QUANTIZATION_DECIMALS = 8


@dataclass(frozen=True, slots=True)
class GeometryHypothesisV3:
    kind: Literal["identity", "pure_resize", "center_crop", "sync"]
    image: NDArray[np.uint8]
    source_to_canonical: NDArray[np.float64]
    score: float


def geometry_hypotheses_v3(
    page: NDArray[np.uint8],
    key: bytes,
    page_index: int,
    canonical_shape: tuple[int, int],
    profile: FingerprintV3Profile,
    orb_template: SyncTemplate | None = None,
) -> tuple[GeometryHypothesisV3, ...]:
    """Return a bounded, shape-prior-first set of canonical V3 candidates."""

    attacked = _validate_page(page)
    canonical_height, canonical_width = _validate_shape(canonical_shape)
    _validate_key(key)
    _validate_page_index(page_index)
    pilot_profile = v2_pilot_profile(profile)
    interpolation = _resize_interpolation(profile.resize_interpolation)

    source_height, source_width = attacked.shape[:2]
    source_shape = (source_height, source_width)
    target_shape = (canonical_height, canonical_width)
    hypotheses: list[GeometryHypothesisV3] = []
    seen_matrices: set[tuple[float, ...]] = set()

    def add(
        kind: Literal["identity", "pure_resize", "center_crop", "sync"],
        image: NDArray[np.uint8],
        matrix: NDArray[np.float64],
        score: float,
    ) -> None:
        if len(hypotheses) >= profile.max_geometry_hypotheses:
            return
        normalized = _normalize_matrix(matrix)
        if normalized is None:
            return
        matrix_key = _quantized_matrix_key(normalized)
        if matrix_key in seen_matrices:
            return
        seen_matrices.add(matrix_key)
        hypotheses.append(
            GeometryHypothesisV3(
                kind=kind,
                image=np.ascontiguousarray(image, dtype=np.uint8),
                source_to_canonical=normalized,
                score=float(score),
            )
        )

    if source_shape == target_shape:
        add("identity", attacked, np.eye(3, dtype=np.float64), 1.0)

    ratio_y = source_height / canonical_height
    ratio_x = source_width / canonical_width
    ratios_agree = _ratios_agree(
        ratio_y, ratio_x, profile.geometry_ratio_tolerance
    )
    if source_shape != target_shape and ratios_agree:
        scale_y = canonical_height / source_height
        scale_x = canonical_width / source_width
        resized = cv2.resize(
            attacked,
            (canonical_width, canonical_height),
            interpolation=interpolation,
        )
        resize_matrix = np.array(
            [
                [scale_x, 0.0, (scale_x - 1.0) / 2.0],
                [0.0, scale_y, (scale_y - 1.0) / 2.0],
                [0.0, 0.0, 1.0],
            ],
            dtype=np.float64,
        )
        add("pure_resize", resized, resize_matrix, 1.0)

    if len(hypotheses) >= profile.max_geometry_hypotheses:
        return tuple(hypotheses)

    if ratios_agree and source_height <= canonical_height and source_width <= canonical_width:
        for retained_scale in profile.crop_retained_scales:
            if not (
                _ratios_agree(
                    ratio_y,
                    retained_scale,
                    profile.geometry_ratio_tolerance,
                )
                and _ratios_agree(
                    ratio_x,
                    retained_scale,
                    profile.geometry_ratio_tolerance,
                )
            ):
                continue
            y0 = (canonical_height - source_height) // 2
            x0 = (canonical_width - source_width) // 2
            canvas = np.full(
                (canonical_height, canonical_width, 3), 255, dtype=np.uint8
            )
            canvas[y0 : y0 + source_height, x0 : x0 + source_width] = attacked
            crop_matrix = np.array(
                [
                    [1.0, 0.0, float(x0)],
                    [0.0, 1.0, float(y0)],
                    [0.0, 0.0, 1.0],
                ],
                dtype=np.float64,
            )
            add("center_crop", canvas, crop_matrix, 1.0)
            if len(hypotheses) >= profile.max_geometry_hypotheses:
                break

    if len(hypotheses) >= profile.max_geometry_hypotheses:
        return tuple(hypotheses)

    fallback = align_page_v2(
        attacked,
        key,
        page_index,
        pilot_profile,
        target_shape,
        orb_template,
    )
    if (
        fallback.reason == "aligned"
        and _is_canonical_image(fallback.image, target_shape)
        and fallback.homography is not None
        and math.isfinite(float(fallback.pilot_score))
    ):
        add(
            "sync",
            fallback.image,
            fallback.homography,
            float(fallback.pilot_score),
        )
    return tuple(hypotheses)


def _validate_page(page: object) -> NDArray[np.uint8]:
    if not isinstance(page, np.ndarray):
        raise TypeError("page must be a numpy array")
    if page.ndim != 3 or page.shape[2] != 3:
        raise ValueError("page must have BGR shape (height, width, 3)")
    if page.dtype != np.uint8:
        raise TypeError("page dtype must be uint8")
    height, width = page.shape[:2]
    if height <= 0 or width <= 0:
        raise ValueError("page must have non-empty dimensions")
    if height * width > _MAX_PAGE_PIXELS:
        raise ValueError("page exceeds the 40-megapixel processing ceiling")
    return page


def _validate_shape(shape: object) -> tuple[int, int]:
    if not isinstance(shape, tuple) or len(shape) != 2:
        raise ValueError("canonical_shape must contain height and width")
    height, width = shape
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0
        for value in (height, width)
    ):
        raise ValueError("canonical_shape dimensions must be positive integers")
    if height * width > _MAX_PAGE_PIXELS:
        raise ValueError("canonical_shape exceeds the 40-megapixel processing ceiling")
    return height, width


def _validate_key(key: object) -> None:
    if not isinstance(key, bytes) or not key:
        raise ValueError("key must be non-empty bytes")


def _validate_page_index(page_index: object) -> None:
    if (
        isinstance(page_index, bool)
        or not isinstance(page_index, int)
        or not 0 <= page_index <= 0xFFFFFFFF
    ):
        raise ValueError("page_index must fit an unsigned 32-bit integer")


def _resize_interpolation(name: str) -> int:
    if name != "INTER_CUBIC":
        raise ValueError("V3 geometry supports only INTER_CUBIC resize interpolation")
    return cv2.INTER_CUBIC


def _ratios_agree(first: float, second: float, tolerance: float) -> bool:
    return math.isclose(first, second, rel_tol=tolerance, abs_tol=tolerance)


def _normalize_matrix(matrix: object) -> NDArray[np.float64] | None:
    values = np.asarray(matrix)
    if values.shape != (3, 3) or not np.issubdtype(values.dtype, np.number):
        return None
    normalized = np.asarray(values, dtype=np.float64)
    if not np.isfinite(normalized).all():
        return None
    divisor = float(normalized[2, 2])
    if not math.isfinite(divisor) or abs(divisor) <= 1e-12:
        return None
    return np.ascontiguousarray(normalized / divisor, dtype=np.float64)


def _quantized_matrix_key(matrix: NDArray[np.float64]) -> tuple[float, ...]:
    return tuple(
        float(value)
        for value in np.round(matrix, decimals=_MATRIX_QUANTIZATION_DECIMALS).flat
    )


def _is_canonical_image(image: object, shape: tuple[int, int]) -> bool:
    return (
        isinstance(image, np.ndarray)
        and image.dtype == np.uint8
        and image.shape == (shape[0], shape[1], 3)
    )
