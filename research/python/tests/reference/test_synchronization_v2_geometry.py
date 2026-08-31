from __future__ import annotations

import cv2
import numpy as np
import pytest

import splitbind_ref.synchronization_v2 as synchronization_v2
from splitbind_attack.attacks import AttackCase, apply_attack
from splitbind_ref.fingerprint_v2_profile import load_v2_profiles
from splitbind_ref.synchronization import SyncTemplate
from splitbind_ref.synchronization_v2 import (
    AlignmentV2Result,
    GeometryHypothesisV2,
    align_page_v2,
    embed_pilot_v2,
    synthesize_pilot_v2,
)


KEY = bytes(range(32))


@pytest.fixture
def profile():
    return load_v2_profiles()[0]


@pytest.fixture
def embedded_gradient(profile):
    height, width = 384, 512
    y, x = np.indices((height, width), dtype=np.float64)
    luminance = 32.0 + 170.0 * x / (width - 1) + 45.0 * y / (height - 1)
    template = synthesize_pilot_v2((height, width), KEY, 0, profile)
    embedded = embed_pilot_v2(luminance, template, profile.pilot_strength_rms)
    raster = np.floor(embedded + 0.5).clip(0, 255).astype(np.uint8)
    return np.repeat(raster[..., None], 3, axis=2)


def _forward_similarity(
    shape: tuple[int, int], scale: float, degrees: float, tx: float, ty: float
) -> np.ndarray:
    height, width = shape
    affine = cv2.getRotationMatrix2D(
        ((width - 1.0) / 2.0, (height - 1.0) / 2.0), degrees, scale
    )
    affine[:, 2] += np.array([tx, ty], dtype=np.float64)
    return np.vstack((affine, np.array([0.0, 0.0, 1.0])))


def _warp_seeded(
    page: np.ndarray, scale: float, degrees: float, tx: float, ty: float
) -> tuple[np.ndarray, np.ndarray]:
    forward = _forward_similarity(page.shape[:2], scale, degrees, tx, ty)
    height, width = page.shape[:2]
    attacked = cv2.warpPerspective(
        page,
        forward,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(127, 127, 127),
    )
    return attacked, np.linalg.inv(forward)


def _corner_rmse(
    measured: np.ndarray, expected: np.ndarray, source_shape: tuple[int, int]
) -> float:
    height, width = source_shape
    corners = np.array(
        [[[0.0, 0.0]], [[width - 1.0, 0.0]], [[width - 1.0, height - 1.0]], [[0.0, height - 1.0]]],
        dtype=np.float64,
    )
    measured_corners = cv2.perspectiveTransform(corners, measured)
    expected_corners = cv2.perspectiveTransform(corners, expected)
    return float(
        np.sqrt(np.mean(np.sum((measured_corners - expected_corners) ** 2, axis=2)))
    )


@pytest.mark.parametrize(
    ("scale", "degrees", "tx", "ty"),
    [
        (0.75, 0.0, 0.0, 0.0),
        (1.50, 3.0, 17.0, -11.0),
        (1.00, -5.0, -9.0, 13.0),
    ],
)
def test_pilot_recovers_bounded_similarity_transform(
    embedded_gradient, profile, scale, degrees, tx, ty
):
    attacked, expected_inverse = _warp_seeded(
        embedded_gradient, scale, degrees, tx, ty
    )

    result = align_page_v2(
        attacked, KEY, 0, profile, embedded_gradient.shape[:2]
    )

    assert result.reason == "aligned"
    assert result.image is not None
    assert result.image.shape == embedded_gradient.shape
    assert result.homography is not None
    assert _corner_rmse(result.homography, expected_inverse, attacked.shape[:2]) <= 3.0


def test_pilot_recovers_centered_crop_25(embedded_gradient, profile):
    height, width = embedded_gradient.shape[:2]
    artifact = apply_attack(
        embedded_gradient,
        AttackCase("crop-25", "crop", {"fraction": 0.25}),
        np.random.default_rng(20260831),
    )
    attacked = artifact.image
    crop_y = (height - attacked.shape[0]) // 2
    crop_x = (width - attacked.shape[1]) // 2
    expected = np.array(
        [[1.0, 0.0, crop_x], [0.0, 1.0, crop_y], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )

    result = align_page_v2(attacked, KEY, 0, profile, (height, width))

    assert result.reason == "aligned"
    assert result.homography is not None
    assert _corner_rmse(result.homography, expected, attacked.shape[:2]) <= 3.0
    assert artifact.removed_area_fraction == pytest.approx(0.25, abs=0.005)


@pytest.mark.parametrize(
    ("tx_fraction", "ty_fraction"),
    [
        (0.51, 0.0),
        (-0.51, 0.0),
        (0.60, 0.0),
        (-0.60, 0.0),
        (0.0, 0.60),
        (0.0, -0.60),
    ],
)
def test_pilot_recovers_translation_beyond_cyclic_half_period(
    embedded_gradient, profile, tx_fraction, ty_fraction
):
    height, width = embedded_gradient.shape[:2]
    attacked, expected_inverse = _warp_seeded(
        embedded_gradient,
        1.0,
        0.0,
        tx_fraction * width,
        ty_fraction * height,
    )

    result = align_page_v2(
        attacked, KEY, 0, profile, embedded_gradient.shape[:2]
    )

    assert result.reason == "aligned"
    assert result.homography is not None
    assert _corner_rmse(result.homography, expected_inverse, attacked.shape[:2]) <= 3.0


def test_pilot_recovers_jpeg_70_plus_resize_75(embedded_gradient, profile):
    resized = cv2.resize(
        embedded_gradient, None, fx=0.75, fy=0.75, interpolation=cv2.INTER_AREA
    )
    encoded, payload = cv2.imencode(
        ".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, 70]
    )
    assert encoded
    attacked = cv2.imdecode(payload, cv2.IMREAD_COLOR)
    expected = np.array(
        [[1.0 / 0.75, 0.0, 0.0], [0.0, 1.0 / 0.75, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )

    result = align_page_v2(
        attacked, KEY, 0, profile, embedded_gradient.shape[:2]
    )

    assert result.reason == "aligned"
    assert result.homography is not None
    assert _corner_rmse(result.homography, expected, attacked.shape[:2]) <= 3.0


def test_log_polar_estimator_does_not_collapse_to_single_peak_api(
    embedded_gradient, profile, monkeypatch
):
    def forbidden_single_peak(*_args, **_kwargs):
        raise AssertionError("log-polar estimation must inspect a multi-peak surface")

    monkeypatch.setattr(cv2, "phaseCorrelate", forbidden_single_peak)

    result = align_page_v2(
        embedded_gradient, KEY, 0, profile, embedded_gradient.shape[:2]
    )

    assert result.reason == "aligned"


def test_log_polar_peak_nms_keeps_three_separated_cyclic_maxima():
    surface = np.zeros((12, 12), dtype=np.float64)
    surface[0, 0] = 1.0
    surface[11, 11] = 0.99
    surface[3, 6] = 0.80
    surface[8, 9] = 0.70
    surface[9, 3] = 0.60

    peaks = synchronization_v2._cyclic_nms_peaks(
        surface, maximum=3, radius_x=2, radius_y=2
    )

    assert peaks == ((0, 0, 1.0), (6, 3, 0.8), (9, 8, 0.7))


def test_refinement_does_not_spend_hypothesis_cap_on_duplicate_geometry(
    embedded_gradient, profile
):
    template = synthesize_pilot_v2(embedded_gradient.shape[:2], KEY, 0, profile)
    hypotheses = synchronization_v2._pilot_hypotheses_v2(
        embedded_gradient[..., 0], template, profile
    )

    for index, hypothesis in enumerate(hypotheses):
        assert all(
            not np.allclose(
                hypothesis.homography,
                other.homography,
                rtol=1e-5,
                atol=1e-3,
            )
            for other in hypotheses[index + 1 :]
        )


def test_all_geometry_fft_inputs_obey_2048_long_edge(profile, monkeypatch):
    shape = (129, 2049)
    template = synthesize_pilot_v2(shape, KEY, 0, profile)
    embedded = embed_pilot_v2(
        np.full(shape, 127.0), template, profile.pilot_strength_rms
    )
    luminance = np.floor(embedded + 0.5).clip(0, 255).astype(np.uint8)
    observed_shapes = []
    real_fft2 = np.fft.fft2

    def recording_fft2(array, *args, **kwargs):
        observed_shapes.append(array.shape)
        return real_fft2(array, *args, **kwargs)

    monkeypatch.setattr(synchronization_v2.np.fft, "fft2", recording_fft2)

    synchronization_v2._refine_similarity_from_pilot_peaks(
        luminance, template, 1.0, 0.0
    )
    synchronization_v2._translation_and_score_hypothesis(
        luminance, template, 1.0, 0.0
    )

    assert observed_shapes
    assert all(max(shape) <= 2048 for shape in observed_shapes)


def test_align_uses_direct_bounded_pilot_at_exact_40_megapixels(
    profile, monkeypatch
):
    canonical_shape = (5000, 8000)
    rendered_shapes = []
    observed_templates = []

    def forbid_full_canonical_synthesis(*_args, **_kwargs):
        raise AssertionError("alignment must not synthesize a full canonical pilot")

    def record_bounded_synthesis(height, width, *_args, **_kwargs):
        rendered_shapes.append((height, width))
        assert max(height, width) <= 2048
        return np.zeros((height, width), dtype=np.float64)

    def no_hypotheses(_luminance, template, _profile):
        observed_templates.append(template)
        return ()

    monkeypatch.setattr(
        synchronization_v2, "synthesize_pilot_v2", forbid_full_canonical_synthesis
    )
    monkeypatch.setattr(
        synchronization_v2, "_synthesize_spatial", record_bounded_synthesis
    )
    monkeypatch.setattr(
        synchronization_v2, "_pilot_hypotheses_v2", no_hypotheses
    )

    result = align_page_v2(
        np.zeros((1, 1, 3), dtype=np.uint8),
        KEY,
        0,
        profile,
        canonical_shape,
    )

    assert result.reason == "insufficient_sync_evidence"
    assert rendered_shapes == [(1280, 2048)]
    assert len(observed_templates) == 1
    assert observed_templates[0].page_shape == canonical_shape
    assert observed_templates[0].spatial.shape == (1280, 2048)


def test_align_rejects_canonical_shape_over_40_megapixels_before_synthesis(
    profile, monkeypatch
):
    monkeypatch.setattr(
        synchronization_v2,
        "synthesize_pilot_v2",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("oversized canonical shape reached pilot synthesis")
        ),
    )

    with pytest.raises(ValueError, match="40-megapixel"):
        align_page_v2(
            np.zeros((1, 1, 3), dtype=np.uint8),
            KEY,
            0,
            profile,
            (5000, 8001),
        )


@pytest.mark.parametrize(
    ("page_factory", "key"),
    [
        (lambda embedded: embedded, b"w" * 32),
        (lambda embedded: np.full_like(embedded, 127), KEY),
    ],
    ids=["wrong-key", "blank"],
)
def test_weak_or_absent_pilot_never_aligns(
    embedded_gradient, profile, page_factory, key
):
    page = page_factory(embedded_gradient)

    result = align_page_v2(page, key, 0, profile, embedded_gradient.shape[:2])

    assert result.reason == "insufficient_sync_evidence"
    assert result.image is None
    assert result.homography is None
    assert result.pilot_score < profile.pilot_score_min


@pytest.mark.parametrize(
    "forward",
    [
        np.array([[-1.0, 0.0, 511.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]),
        np.diag([0.44, 0.44, 1.0]),
        np.diag([1.61, 1.61, 1.0]),
        _forward_similarity((384, 512), 1.0, 8.1, 0.0, 0.0),
        _forward_similarity((384, 512), 1.0, -8.1, 0.0, 0.0),
        np.array([[1.0, 0.0, 0.61 * 512], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]),
        np.array([[1.0, 0.0, 0.0], [0.0, 1.0, -0.61 * 384], [0.0, 0.0, 1.0]]),
        np.array([[1.0, 0.0, np.nan], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]),
    ],
    ids=[
        "reflection",
        "scale-low",
        "scale-high",
        "rotation-high",
        "rotation-low",
        "translation-x",
        "translation-y",
        "nonfinite",
    ],
)
def test_geometry_gate_rejects_out_of_contract_similarity(forward):
    inverse = np.linalg.inv(forward) if np.isfinite(forward).all() else forward

    assert not synchronization_v2._geometry_is_acceptable_v2(
        inverse, (384, 512), (384, 512)
    )


def test_geometry_gate_rejects_clustered_orb_evidence():
    source = np.array(
        [[[10.0 + index % 3, 12.0 + index // 3]] for index in range(12)],
        dtype=np.float64,
    )
    target = source.copy()
    inliers = np.ones((12, 1), dtype=np.uint8)

    assert not synchronization_v2._orb_geometry_is_acceptable_v2(
        np.eye(3), source, target, inliers, (384, 512), (384, 512)
    )


def test_geometry_gate_accepts_exact_translation_contract_corner():
    forward = np.array(
        [
            [1.0, 0.0, 0.60 * 512],
            [0.0, 1.0, -0.30 * 384],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )

    assert synchronization_v2._geometry_is_acceptable_v2(
        np.linalg.inv(forward), (384, 512), (384, 512)
    )


def test_geometry_gate_accepts_small_projective_residual_within_three_pixels():
    forward = np.array(
        [
            [1.0, 0.0, 7.0],
            [0.0, 1.0, -5.0],
            [1e-6, -1e-6, 1.0],
        ],
        dtype=np.float64,
    )

    assert synchronization_v2._geometry_is_acceptable_v2(
        np.linalg.inv(forward), (384, 512), (384, 512)
    )


@pytest.mark.parametrize(
    "matrix",
    [
        np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 0.0]]),
        np.array([[1e-10, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]),
        np.array([[1.0, 0.25, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]),
    ],
    ids=["zero-divisor", "ill-conditioned", "non-similarity"],
)
def test_geometry_gate_rejects_unsafe_matrix_before_normalization(matrix):
    assert not synchronization_v2._geometry_is_acceptable_v2(
        matrix, (384, 512), (384, 512)
    )


def test_low_correlation_hypothesis_never_reaches_warp(
    embedded_gradient, profile, monkeypatch
):
    weak = GeometryHypothesisV2(np.eye(3), profile.pilot_score_min - 0.01, "pilot")
    monkeypatch.setattr(
        synchronization_v2, "_pilot_hypotheses_v2", lambda *_args, **_kwargs: [weak]
    )
    monkeypatch.setattr(
        cv2,
        "warpPerspective",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("weak evidence must not reach warpPerspective")
        ),
    )

    result = align_page_v2(
        embedded_gradient, KEY, 0, profile, embedded_gradient.shape[:2]
    )

    assert result.reason == "insufficient_sync_evidence"
    assert result.image is None
    assert result.homography is None


@pytest.mark.parametrize(
    "matrix",
    [
        np.array([[-1.0, 0.0, 511.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]),
        np.diag([1.0 / 0.44, 1.0 / 0.44, 1.0]),
        np.array([[1.0, 0.0, np.nan], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]),
    ],
    ids=["reflection", "scale", "nonfinite"],
)
def test_rejected_hypothesis_never_reaches_warp(
    embedded_gradient, profile, monkeypatch, matrix
):
    rejected = GeometryHypothesisV2(matrix, 1.0, "pilot")
    monkeypatch.setattr(
        synchronization_v2,
        "_pilot_hypotheses_v2",
        lambda *_args, **_kwargs: [rejected],
    )
    monkeypatch.setattr(
        cv2,
        "warpPerspective",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("rejected geometry must not reach warpPerspective")
        ),
    )

    result = align_page_v2(
        embedded_gradient, KEY, 0, profile, embedded_gradient.shape[:2]
    )

    assert result.reason == "geometry_rejected"
    assert result.image is None
    assert result.homography is None


def test_alignment_caps_hypotheses_and_warps_only_one_winner(
    embedded_gradient, profile, monkeypatch
):
    pilot_hypotheses = [
        GeometryHypothesisV2(np.eye(3), 0.30 + 0.01 * index, "pilot")
        for index in range(5)
    ]
    orb = GeometryHypothesisV2(np.eye(3), 0.0, "orb")
    monkeypatch.setattr(
        synchronization_v2,
        "_pilot_hypotheses_v2",
        lambda *_args, **_kwargs: pilot_hypotheses,
    )
    monkeypatch.setattr(
        synchronization_v2, "_orb_hypothesis_v2", lambda *_args, **_kwargs: orb
    )
    template = SyncTemplate(
        embedded_gradient.shape[:2],
        np.array([[0, 0], [511, 0], [511, 383], [0, 383]], dtype=np.float32),
        np.zeros((4, 32), dtype=np.uint8),
    )
    real_warp = cv2.warpPerspective
    warp_calls = 0

    def recording_warp(*args, **kwargs):
        nonlocal warp_calls
        warp_calls += 1
        return real_warp(*args, **kwargs)

    monkeypatch.setattr(cv2, "warpPerspective", recording_warp)

    result = align_page_v2(
        embedded_gradient,
        KEY,
        0,
        profile,
        embedded_gradient.shape[:2],
        orb_template=template,
    )

    assert result.reason == "aligned"
    assert result.hypothesis_count == 4
    assert warp_calls == 1


@pytest.mark.parametrize(
    ("failure_stage", "expected_hypothesis_count"),
    [
        ("pilot_estimation", 0),
        ("orb_estimation", 1),
        ("geometry_validation", 1),
        ("canonical_warp", 1),
    ],
)
def test_opencv_runtime_failures_raise_typed_alignment_error(
    embedded_gradient,
    profile,
    monkeypatch,
    failure_stage,
    expected_hypothesis_count,
):
    def fail(*_args, **_kwargs):
        raise cv2.error(f"{failure_stage} failure")

    valid = GeometryHypothesisV2(np.eye(3), 1.0, "pilot")
    orb_template = None
    if failure_stage == "pilot_estimation":
        monkeypatch.setattr(synchronization_v2, "_pilot_hypotheses_v2", fail)
    else:
        monkeypatch.setattr(
            synchronization_v2,
            "_pilot_hypotheses_v2",
            lambda *_args, **_kwargs: [valid],
        )
        if failure_stage == "orb_estimation":
            orb_template = SyncTemplate(
                embedded_gradient.shape[:2],
                np.array(
                    [[0, 0], [511, 0], [511, 383], [0, 383]], dtype=np.float32
                ),
                np.zeros((4, 32), dtype=np.uint8),
            )
            monkeypatch.setattr(synchronization_v2, "_orb_hypothesis_v2", fail)
        elif failure_stage == "geometry_validation":
            monkeypatch.setattr(
                synchronization_v2, "_geometry_is_acceptable_v2", fail
            )
        else:
            monkeypatch.setattr(cv2, "warpPerspective", fail)

    runtime_error_type = getattr(
        synchronization_v2, "AlignmentV2RuntimeError", None
    )
    assert runtime_error_type is not None
    with pytest.raises(runtime_error_type) as captured:
        align_page_v2(
            embedded_gradient,
            KEY,
            0,
            profile,
            embedded_gradient.shape[:2],
            orb_template=orb_template,
        )

    assert captured.value.stage == failure_stage
    assert captured.value.hypothesis_count == expected_hypothesis_count
    assert isinstance(captured.value.__cause__, cv2.error)


def test_missing_orb_features_remain_ordinary_insufficient_evidence(
    embedded_gradient, profile, monkeypatch
):
    monkeypatch.setattr(
        synchronization_v2, "_pilot_hypotheses_v2", lambda *_args, **_kwargs: []
    )
    monkeypatch.setattr(
        synchronization_v2, "_orb_hypothesis_v2", lambda *_args, **_kwargs: None
    )
    template = SyncTemplate(
        embedded_gradient.shape[:2],
        np.array([[0, 0], [511, 0], [511, 383], [0, 383]], dtype=np.float32),
        np.zeros((4, 32), dtype=np.uint8),
    )

    result = align_page_v2(
        embedded_gradient,
        KEY,
        0,
        profile,
        embedded_gradient.shape[:2],
        orb_template=template,
    )

    assert result == AlignmentV2Result(
        None, None, 0.0, 0, "insufficient_sync_evidence"
    )
