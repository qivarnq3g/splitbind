import math

import numpy as np
import pytest

from splitbind_attack.ground_truth import NormalizedRect
from splitbind_bench.metrics import (
    Result,
    compute_detection_metrics,
    compute_localization_iou,
    compute_quality_metrics,
)


def test_false_attribution_is_counted_separately_from_non_decodes():
    rows = [
        Result(expected="a", decoded="a", reason="decoded"),
        Result(expected="a", decoded=None, reason="not_detected"),
        Result(expected="a", decoded=None, reason="partial"),
        Result(expected="a", decoded=None, reason="invalid_crc"),
        Result(expected="a", decoded="b", reason="decoded"),
        Result(expected=None, decoded="c", reason="decoded"),
        Result(expected=None, decoded=None, reason="not_detected"),
    ]

    metrics = compute_detection_metrics(rows)

    assert metrics.true_attribution == 1
    assert metrics.missed_detection == 3
    assert metrics.false_attribution == 2
    assert metrics.not_detected == 2
    assert metrics.partial == 1
    assert metrics.invalid_crc == 1


def test_decode_rate_denominator_includes_every_eligible_positive_case():
    rows = [
        Result(expected="a", decoded="a", reason="decoded"),
        Result(expected="a", decoded=None, reason="not_detected"),
        Result(expected="a", decoded=None, reason="partial"),
        Result(expected="a", decoded="b", reason="decoded"),
        Result(expected="a", decoded="a", reason="decoded", eligible=False),
        Result(expected=None, decoded=None, reason="not_detected"),
    ]

    metrics = compute_detection_metrics(rows)

    assert metrics.eligible_positive_cases == 4
    assert metrics.decode_rate == pytest.approx(0.25)
    assert metrics.eligible_evaluated_cases == 5
    assert metrics.scheduled_evaluated_cases == 6
    assert metrics.false_attribution_rate == pytest.approx(1.0 / 6.0)


def test_positive_execution_error_is_a_missed_detection_in_the_denominator():
    metrics = compute_detection_metrics(
        [
            Result(
                expected="a",
                decoded=None,
                reason="execution_error",
                eligible=False,
            )
        ]
    )

    assert metrics.eligible_positive_cases == 0
    assert metrics.decode_denominator_positive_cases == 1
    assert metrics.missed_detection == 1
    assert metrics.execution_errors == 1
    assert metrics.decode_rate == 0.0


def test_wrong_non_null_id_is_false_attribution_even_when_crop_is_ineligible():
    metrics = compute_detection_metrics(
        [Result(expected="a", decoded="b", reason="decoded", eligible=False)]
    )

    assert metrics.eligible_positive_cases == 0
    assert metrics.false_attribution == 1
    assert metrics.scheduled_evaluated_cases == 1
    assert metrics.false_attribution_rate == 1.0


def test_identical_uint8_images_have_perfect_quality():
    image = np.arange(16 * 16 * 3, dtype=np.uint8).reshape(16, 16, 3)

    quality = compute_quality_metrics(image, image)

    assert math.isinf(quality.psnr_db)
    assert quality.ssim == 1.0
    assert quality.data_range == 255.0


def test_quality_uses_uint16_dynamic_range_and_requires_alignment():
    original = np.zeros((16, 16), dtype=np.uint16)
    changed = original.copy()
    changed[0, 0] = 1

    quality = compute_quality_metrics(original, changed)
    expected_mse = 1.0 / (16 * 16)
    expected_psnr = 10.0 * math.log10(65535.0**2 / expected_mse)

    assert quality.psnr_db == pytest.approx(expected_psnr)
    assert quality.data_range == 65535.0
    with pytest.raises(ValueError, match="aligned dimensions"):
        compute_quality_metrics(original, changed[:, :-1])


def test_localization_iou_uses_the_union_of_normalized_rectangles():
    expected = (NormalizedRect(0.0, 0.0, 0.5, 0.5),)
    predicted = (NormalizedRect(0.25, 0.25, 0.5, 0.5),)

    # Intersection = 0.25 * 0.25 = 0.0625; union = 0.25 + 0.25 - 0.0625.
    assert compute_localization_iou(expected, predicted) == pytest.approx(1.0 / 7.0)


@pytest.mark.parametrize(
    "rect",
    [
        (-0.01, 0.0, 0.5, 0.5),
        (0.0, 0.0, 0.0, 0.5),
        (0.8, 0.8, 0.3, 0.3),
    ],
)
def test_normalized_rect_rejects_out_of_bounds_or_empty_geometry(rect):
    with pytest.raises(ValueError, match="normalized"):
        NormalizedRect(*rect)
