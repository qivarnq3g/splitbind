import numpy as np
import pytest

from splitbind_attack.attacks import AttackCase, apply_attack
from splitbind_attack.ground_truth import NormalizedRect


@pytest.fixture
def sample_image():
    y, x = np.indices((120, 160), dtype=np.uint16)
    image = np.empty((120, 160, 3), dtype=np.uint8)
    image[..., 0] = (x * 3 + y) % 256
    image[..., 1] = (x + y * 5) % 256
    image[..., 2] = (x * 7 + y * 2) % 256
    return image


@pytest.mark.parametrize(
    ("case", "expected_shape"),
    [
        (AttackCase("jpeg-70", "jpeg", {"quality": 70}), (120, 160, 3)),
        (AttackCase("resize-075", "resize", {"scale": 0.75}), (90, 120, 3)),
        (AttackCase("rotate-3", "rotation", {"degrees": 3}), (120, 160, 3)),
        (
            AttackCase(
                "brightness-contrast",
                "brightness_contrast",
                {"brightness_factor": 0.85, "contrast_factor": 0.9},
            ),
            (120, 160, 3),
        ),
        (
            AttackCase(
                "noise-blur",
                "noise_blur",
                {"noise_sigma": 8.0, "blur_sigma": 0.8},
            ),
            (120, 160, 3),
        ),
        (
            AttackCase(
                "screen-1366x768",
                "screenshot",
                {"kind": "raster", "width_px": 1366, "height_px": 768},
            ),
            (768, 1366, 3),
        ),
        (
            AttackCase(
                "screen-perspective",
                "screenshot",
                {
                    "kind": "perspective",
                    "width_px": 320,
                    "height_px": 180,
                    "corner_offsets": [
                        [0.03, 0.02],
                        [-0.02, 0.04],
                        [-0.03, -0.02],
                        [0.02, -0.03],
                    ],
                },
            ),
            (180, 320, 3),
        ),
    ],
)
def test_each_raster_attack_preserves_uint8_bgr_and_reports_operation(
    sample_image, case, expected_shape
):
    before = sample_image.copy()

    artifact = apply_attack(sample_image, case, np.random.default_rng(17))

    assert artifact.image.shape == expected_shape
    assert artifact.image.dtype == np.uint8
    assert artifact.image.flags.c_contiguous
    assert artifact.operations == (case.kind,)
    assert np.array_equal(sample_image, before)


def test_crop_fraction_means_removed_area_and_reports_retained_geometry(sample_image):
    artifact = apply_attack(
        sample_image,
        AttackCase("crop-25", "crop", {"fraction": 0.25}),
        np.random.default_rng(1),
    )

    assert artifact.image.shape == (104, 139, 3)
    assert artifact.retained_region is not None
    assert artifact.retained_region.width * artifact.retained_region.height == pytest.approx(
        (139 * 104) / (160 * 120)
    )
    assert artifact.removed_area_fraction == pytest.approx(
        1.0 - (139 * 104) / (160 * 120)
    )


def test_randomized_noise_is_reproducible_and_domain_seed_sensitive(sample_image):
    case = AttackCase(
        "noise-8-blur-08",
        "noise_blur",
        {"noise_sigma": 8.0, "blur_sigma": 0.8},
    )

    first = apply_attack(sample_image, case, np.random.default_rng(20260827))
    second = apply_attack(sample_image, case, np.random.default_rng(20260827))
    different = apply_attack(sample_image, case, np.random.default_rng(20260828))

    assert np.array_equal(first.image, second.image)
    assert not np.array_equal(first.image, different.image)


@pytest.mark.parametrize(
    ("kind", "region"),
    [
        ("replace_text", {"x": 0.15, "y": 0.15, "width": 0.35, "height": 0.1}),
        ("cover_region", {"x": 0.55, "y": 0.2, "width": 0.25, "height": 0.2}),
        ("copy_move", {"x": 0.2, "y": 0.55, "width": 0.2, "height": 0.2}),
        ("insert_object", {"x": 0.6, "y": 0.6, "width": 0.25, "height": 0.2}),
    ],
)
def test_tamper_attacks_change_the_declared_region_and_emit_ground_truth(
    sample_image, kind, region
):
    case = AttackCase(f"tamper-{kind}", "tamper", {"kind": kind, "region": region})

    artifact = apply_attack(sample_image, case, np.random.default_rng(9))

    expected = NormalizedRect(**region)
    assert artifact.ground_truth == (expected,)
    x0 = round(expected.x * sample_image.shape[1])
    y0 = round(expected.y * sample_image.shape[0])
    x1 = round(expected.right * sample_image.shape[1])
    y1 = round(expected.bottom * sample_image.shape[0])
    assert not np.array_equal(
        artifact.image[y0:y1, x0:x1], sample_image[y0:y1, x0:x1]
    )


def test_combined_attack_preserves_order_and_is_repeatable(sample_image):
    case = AttackCase(
        "combined-jpeg-crop",
        "combined",
        {},
        operations=(
            AttackCase("jpeg", "jpeg", {"quality": 70}),
            AttackCase("crop", "crop", {"fraction": 0.25}),
        ),
    )

    first = apply_attack(sample_image, case, np.random.default_rng(22))
    second = apply_attack(sample_image, case, np.random.default_rng(22))

    assert first.operations == ("jpeg", "crop")
    assert first.image.shape == (104, 139, 3)
    assert np.array_equal(first.image, second.image)


def test_unknown_attack_is_rejected_instead_of_becoming_a_noop(sample_image):
    with pytest.raises(ValueError, match="unsupported attack kind"):
        apply_attack(
            sample_image,
            AttackCase("unknown", "not-real", {}),
            np.random.default_rng(1),
        )
