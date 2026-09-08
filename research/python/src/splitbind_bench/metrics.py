"""Independently defined detection, image-quality, and localization metrics."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Literal

import cv2
import numpy as np
from numpy.typing import NDArray

from splitbind_attack.ground_truth import NormalizedRect


DecisionReason = Literal[
    "decoded", "partial", "not_detected", "invalid_crc", "execution_error"
]


@dataclass(frozen=True, slots=True)
class Result:
    expected: str | None
    decoded: str | None
    reason: DecisionReason
    eligible: bool = True


@dataclass(frozen=True, slots=True)
class DetectionMetrics:
    true_attribution: int
    missed_detection: int
    false_attribution: int
    not_detected: int
    partial: int
    invalid_crc: int
    execution_errors: int
    eligible_positive_cases: int
    decode_denominator_positive_cases: int
    eligible_evaluated_cases: int
    scheduled_evaluated_cases: int
    decode_rate: float | None
    false_attribution_rate: float | None


@dataclass(frozen=True, slots=True)
class QualityMetrics:
    psnr_db: float
    ssim: float
    data_range: float


def compute_detection_metrics(rows: Iterable[Result]) -> DetectionMetrics:
    """Count outcomes without treating a non-decision as a wrong attribution.

    Decode rate is true attributions divided by every geometry-eligible positive
    case plus every scheduled positive execution error.  False attribution is
    counted over every scheduled row, regardless of crop decode eligibility.
    """

    scheduled = tuple(rows)
    if any(not isinstance(row, Result) for row in scheduled):
        raise TypeError("rows must contain Result values")
    evaluated = tuple(row for row in scheduled if row.eligible)
    positive = tuple(
        row
        for row in scheduled
        if row.expected is not None
        and (row.eligible or row.reason == "execution_error")
    )
    true_attribution = sum(row.decoded == row.expected for row in positive)
    missed_detection = sum(row.decoded is None for row in positive)
    false_attribution = sum(
        row.decoded is not None and row.decoded != row.expected for row in scheduled
    )
    not_detected = sum(
        row.decoded is None and row.reason == "not_detected" for row in scheduled
    )
    partial = sum(row.decoded is None and row.reason == "partial" for row in scheduled)
    invalid_crc = sum(
        row.decoded is None and row.reason == "invalid_crc" for row in scheduled
    )
    execution_errors = sum(row.reason == "execution_error" for row in scheduled)
    decode_rate = true_attribution / len(positive) if positive else None
    false_rate = false_attribution / len(scheduled) if scheduled else None
    return DetectionMetrics(
        true_attribution=true_attribution,
        missed_detection=missed_detection,
        false_attribution=false_attribution,
        not_detected=not_detected,
        partial=partial,
        invalid_crc=invalid_crc,
        execution_errors=execution_errors,
        eligible_positive_cases=sum(
            row.expected is not None and row.eligible for row in scheduled
        ),
        decode_denominator_positive_cases=len(positive),
        eligible_evaluated_cases=len(evaluated),
        scheduled_evaluated_cases=len(scheduled),
        decode_rate=decode_rate,
        false_attribution_rate=false_rate,
    )


def compute_quality_metrics(
    original: NDArray[np.generic], watermarked: NDArray[np.generic]
) -> QualityMetrics:
    """Compute PSNR and windowed SSIM over aligned unsigned raster samples.

    PSNR uses the full range of the input unsigned dtype.  SSIM uses the
    standard 11x11 Gaussian window (sigma 1.5), C1=(0.01L)^2 and
    C2=(0.03L)^2, averaged over all pixels and channels.
    """

    if not isinstance(original, np.ndarray) or not isinstance(watermarked, np.ndarray):
        raise TypeError("quality inputs must be numpy arrays")
    if original.shape != watermarked.shape:
        raise ValueError("quality inputs must have aligned dimensions")
    if original.size == 0:
        raise ValueError("quality inputs must be non-empty")
    if original.dtype != watermarked.dtype or original.dtype.kind != "u":
        raise TypeError("quality inputs must share an unsigned integer dtype")
    if original.ndim not in (2, 3) or (original.ndim == 3 and original.shape[2] not in (1, 3, 4)):
        raise ValueError("quality inputs must be grayscale or channel-last images")

    data_range = float(np.iinfo(original.dtype).max)
    channel_indexes: tuple[int | None, ...] = (
        (None,) if original.ndim == 2 else tuple(range(original.shape[2]))
    )
    squared_error = 0.0
    for channel_index in channel_indexes:
        source = original if channel_index is None else original[..., channel_index]
        target = watermarked if channel_index is None else watermarked[..., channel_index]
        difference = source.astype(np.float64) - target.astype(np.float64)
        squared_error += float(np.sum(difference * difference))
    mse = squared_error / original.size
    psnr_db = math.inf if mse == 0.0 else 10.0 * math.log10(data_range**2 / mse)

    c1 = (0.01 * data_range) ** 2
    c2 = (0.03 * data_range) ** 2
    channel_ssim = []
    for channel_index in channel_indexes:
        source = original if channel_index is None else original[..., channel_index]
        target = watermarked if channel_index is None else watermarked[..., channel_index]
        first = source.astype(np.float64)
        second = target.astype(np.float64)
        mu_first = cv2.GaussianBlur(first, (11, 11), 1.5, borderType=cv2.BORDER_REFLECT_101)
        mu_second = cv2.GaussianBlur(second, (11, 11), 1.5, borderType=cv2.BORDER_REFLECT_101)
        mu_first_sq = mu_first * mu_first
        mu_second_sq = mu_second * mu_second
        mu_product = mu_first * mu_second
        sigma_first_sq = cv2.GaussianBlur(
            first * first, (11, 11), 1.5, borderType=cv2.BORDER_REFLECT_101
        ) - mu_first_sq
        sigma_second_sq = cv2.GaussianBlur(
            second * second, (11, 11), 1.5, borderType=cv2.BORDER_REFLECT_101
        ) - mu_second_sq
        covariance = cv2.GaussianBlur(
            first * second, (11, 11), 1.5, borderType=cv2.BORDER_REFLECT_101
        ) - mu_product
        numerator = (2.0 * mu_product + c1) * (2.0 * covariance + c2)
        denominator = (mu_first_sq + mu_second_sq + c1) * (
            sigma_first_sq + sigma_second_sq + c2
        )
        channel_ssim.append(float(np.mean(numerator / denominator)))
    ssim = sum(channel_ssim) / len(channel_ssim)
    if not math.isfinite(ssim):
        raise ValueError("SSIM calculation produced a non-finite value")
    return QualityMetrics(psnr_db=psnr_db, ssim=ssim, data_range=data_range)


def compute_localization_iou(
    expected: Iterable[NormalizedRect], predicted: Iterable[NormalizedRect]
) -> float:
    """Return exact axis-aligned union IoU for normalized rectangle sets."""

    expected_rects = tuple(expected)
    predicted_rects = tuple(predicted)
    if any(not isinstance(rect, NormalizedRect) for rect in expected_rects + predicted_rects):
        raise TypeError("localization regions must be NormalizedRect values")
    if not expected_rects and not predicted_rects:
        return 1.0
    if not expected_rects or not predicted_rects:
        return 0.0
    xs = sorted({value for rect in expected_rects + predicted_rects for value in (rect.x, rect.right)})
    ys = sorted({value for rect in expected_rects + predicted_rects for value in (rect.y, rect.bottom)})
    intersection = 0.0
    union = 0.0
    for x0, x1 in zip(xs, xs[1:]):
        for y0, y1 in zip(ys, ys[1:]):
            midpoint_x = (x0 + x1) / 2.0
            midpoint_y = (y0 + y1) / 2.0
            in_expected = any(
                rect.x <= midpoint_x <= rect.right and rect.y <= midpoint_y <= rect.bottom
                for rect in expected_rects
            )
            in_predicted = any(
                rect.x <= midpoint_x <= rect.right and rect.y <= midpoint_y <= rect.bottom
                for rect in predicted_rects
            )
            area = (x1 - x0) * (y1 - y0)
            if in_expected or in_predicted:
                union += area
            if in_expected and in_predicted:
                intersection += area
    return intersection / union
