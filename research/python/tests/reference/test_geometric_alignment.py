import cv2
import numpy as np
import pytest

import splitbind_ref.synchronization as synchronization_module
from splitbind_ref.synchronization import SyncTemplate, align_page, build_sync_template


def _feature_page() -> np.ndarray:
    y, x = np.indices((512, 512))
    page = np.empty((512, 512, 3), dtype=np.uint8)
    page[..., 0] = (x // 2 + y // 3) % 256
    page[..., 1] = (2 * x // 3 + y // 5) % 256
    page[..., 2] = (x // 7 + 3 * y // 4) % 256
    for offset in range(32, 480, 64):
        page[offset : offset + 5, 24:488] = (245, 245, 245)
        page[24:488, offset : offset + 5] = (12, 12, 12)
    page[80:150, 90:230] = (0, 220, 40)
    page[315:430, 280:455] = (230, 25, 180)
    return page


def test_orb_ransac_alignment_reverses_a_seeded_rotation_and_translation():
    import cv2

    original = _feature_page()
    template = build_sync_template(original)
    transform = cv2.getRotationMatrix2D((255.5, 255.5), 3.0, 1.0)
    transform[:, 2] += np.array([7.0, -5.0])
    attacked = cv2.warpAffine(
        original,
        transform,
        (512, 512),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT_101,
    )

    result = align_page(attacked, template)

    assert result.reason == "aligned"
    assert result.image is not None
    assert result.image.shape == original.shape
    assert result.matched_keypoints >= 20
    assert result.inlier_keypoints >= 12
    expected_homography = np.linalg.inv(
        np.vstack((transform, np.array([0.0, 0.0, 1.0])))
    )
    corners = np.array(
        [[[0.0, 0.0]], [[511.0, 0.0]], [[511.0, 511.0]], [[0.0, 511.0]]],
        dtype=np.float64,
    )
    measured_corners = cv2.perspectiveTransform(corners, result.homography)
    expected_corners = cv2.perspectiveTransform(corners, expected_homography)
    corner_error = np.linalg.norm(measured_corners - expected_corners, axis=2)
    assert float(np.max(corner_error)) < 3.0
    mean_absolute_error = np.mean(
        np.abs(result.image.astype(np.float64) - original.astype(np.float64))
    )
    assert mean_absolute_error < 12.0


def test_alignment_reports_insufficient_features_without_fabricating_a_transform():
    template = build_sync_template(_feature_page())
    blank = np.full((512, 512, 3), 127, dtype=np.uint8)

    result = align_page(blank, template)

    assert result.image is None
    assert result.homography is None
    assert result.reason == "insufficient_features"
    assert result.inlier_keypoints == 0


@pytest.mark.parametrize(
    ("page", "message"),
    [
        (np.zeros((32, 32), dtype=np.uint8), "BGR"),
        (np.zeros((32, 32, 3), dtype=np.float32), "uint8"),
        (np.zeros((0, 32, 3), dtype=np.uint8), "non-empty"),
    ],
)
def test_sync_template_rejects_unsupported_page_shapes_and_types(page, message):
    with pytest.raises((TypeError, ValueError), match=message):
        build_sync_template(page)


@pytest.mark.parametrize(
    ("page_shape", "message"),
    [
        ((True, 512), "positive integers"),
        ((0, 512), "positive integers"),
        ((40_000_001, 1), "40,000,000"),
    ],
)
def test_sync_template_rejects_invalid_or_oversized_page_shape(page_shape, message):
    points = np.zeros((4, 2), dtype=np.float32)
    descriptors = np.zeros((4, 32), dtype=np.uint8)

    with pytest.raises(ValueError, match=message):
        SyncTemplate(page_shape, points, descriptors)


@pytest.mark.parametrize(
    ("points", "descriptors", "message"),
    [
        (np.zeros((4, 2), dtype=np.float64), np.zeros((4, 32), np.uint8), "float32"),
        (np.zeros((4, 3), dtype=np.float32), np.zeros((4, 32), np.uint8), "N x 2"),
        (np.full((4, 2), np.nan, dtype=np.float32), np.zeros((4, 32), np.uint8), "finite"),
        (np.zeros((4, 2), dtype=np.float32), np.zeros((4, 32), np.float32), "uint8"),
        (np.zeros((4, 2), dtype=np.float32), np.zeros((4, 31), np.uint8), "N x 32"),
        (np.zeros((4, 2), dtype=np.float32), np.zeros((5, 32), np.uint8), "matching"),
        (np.zeros((3, 2), dtype=np.float32), np.zeros((3, 32), np.uint8), "between 4 and 1500"),
        (
            np.zeros((1501, 2), dtype=np.float32),
            np.zeros((1501, 32), np.uint8),
            "between 4 and 1500",
        ),
    ],
)
def test_sync_template_rejects_malformed_orb_arrays(points, descriptors, message):
    with pytest.raises(ValueError, match=message):
        SyncTemplate((512, 512), points, descriptors)


def test_sync_template_defensively_copies_contiguous_read_only_arrays():
    points = np.arange(8, dtype=np.float32).reshape(4, 2)
    descriptors = np.arange(128, dtype=np.uint8).reshape(4, 32)

    template = SyncTemplate((512, 512), points, descriptors)
    points[:] = 0
    descriptors[:] = 0

    assert template.keypoints[3].tolist() == [6.0, 7.0]
    assert template.descriptors[3, -1] == 127
    assert template.keypoints.flags.c_contiguous
    assert template.descriptors.flags.c_contiguous
    assert not template.keypoints.flags.writeable
    assert not template.descriptors.flags.writeable


def test_build_sync_template_rejects_over_40_megapixels_before_copying():
    one_pixel = np.zeros((1, 1, 3), dtype=np.uint8)
    oversized_view = np.broadcast_to(one_pixel, (40_000_001, 1, 3))

    with pytest.raises(ValueError, match="40,000,000"):
        build_sync_template(oversized_view)


def test_build_sync_template_caps_opencv_output_at_configured_nfeatures(monkeypatch):
    keypoints = [cv2.KeyPoint(float(index), 1.0, 1.0) for index in range(1501)]
    descriptors = np.zeros((1501, 32), dtype=np.uint8)
    monkeypatch.setattr(
        synchronization_module,
        "_detect",
        lambda _gray: (keypoints, descriptors),
    )

    template = build_sync_template(np.zeros((32, 32, 3), dtype=np.uint8))

    assert template.keypoints.shape == (1500, 2)
    assert template.descriptors.shape == (1500, 32)


def test_align_page_revalidates_a_tampered_template():
    template = build_sync_template(_feature_page())
    object.__setattr__(template, "descriptors", np.zeros((3, 31), dtype=np.uint8))

    with pytest.raises(ValueError, match="descriptors"):
        align_page(_feature_page(), template)


def test_align_page_converts_opencv_failures_to_geometry_failure(monkeypatch):
    template = build_sync_template(_feature_page())

    def fail_detection(_gray):
        raise cv2.error("detector failure")

    monkeypatch.setattr("splitbind_ref.synchronization._detect", fail_detection)

    result = align_page(_feature_page(), template)

    assert result.image is None
    assert result.homography is None
    assert result.reason == "geometry_failure"


def _synthetic_geometry():
    coordinates = np.linspace(48.0, 464.0, 5)
    source = np.array(
        [[[x, y]] for y in coordinates for x in coordinates], dtype=np.float64
    )
    angle = np.deg2rad(-3.0)
    homography = np.array(
        [
            [np.cos(angle), -np.sin(angle), -6.72],
            [np.sin(angle), np.cos(angle), 5.36],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    target = cv2.perspectiveTransform(source, homography)
    inliers = np.ones((source.shape[0], 1), dtype=np.uint8)
    return homography, source, target, inliers


def test_geometry_gate_accepts_a_known_inverse_three_degree_transform():
    homography, source, target, inliers = _synthetic_geometry()

    assert synchronization_module._geometry_is_acceptable(
        homography, source, target, inliers, (512, 512), (512, 512)
    )


def test_geometry_gate_rejects_low_inlier_count_and_ratio():
    homography, source, target, inliers = _synthetic_geometry()
    inliers[:] = 0
    inliers[:7] = 1

    assert not synchronization_module._geometry_is_acceptable(
        homography, source, target, inliers, (512, 512), (512, 512)
    )


def test_geometry_gate_rejects_clustered_source_and_target_evidence():
    homography, source, target, inliers = _synthetic_geometry()
    source[:] = source[:1] + np.arange(source.shape[0]).reshape(-1, 1, 1) % 4
    target = cv2.perspectiveTransform(source, homography)

    assert not synchronization_module._geometry_is_acceptable(
        homography, source, target, inliers, (512, 512), (512, 512)
    )


@pytest.mark.parametrize(
    "bad_homography",
    [
        np.array([[np.nan, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]),
        np.array([[-1.0, 0.0, 511.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]),
        np.array([[1e-8, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]),
        np.array([[1.0, 0.0, 10_000.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]),
    ],
)
def test_geometry_gate_rejects_nonfinite_degenerate_or_extreme_homography(
    bad_homography,
):
    _, source, target, inliers = _synthetic_geometry()

    assert not synchronization_module._geometry_is_acceptable(
        bad_homography, source, target, inliers, (512, 512), (512, 512)
    )


def test_geometry_gate_rejects_excessive_inlier_reprojection_error():
    homography, source, target, inliers = _synthetic_geometry()
    target = target.copy()
    target[::2, 0, 0] += 12.0

    assert not synchronization_module._geometry_is_acceptable(
        homography, source, target, inliers, (512, 512), (512, 512)
    )


def test_rejected_geometry_never_reaches_warp(monkeypatch):
    original = _feature_page()
    template = build_sync_template(original)

    def low_quality_homography(source, target, **_kwargs):
        return np.eye(3), np.ones((source.shape[0], 1), dtype=np.uint8)[:7]

    def forbidden_warp(*_args, **_kwargs):
        raise AssertionError("warp must not run for rejected geometry")

    monkeypatch.setattr(cv2, "findHomography", low_quality_homography)
    monkeypatch.setattr(cv2, "warpPerspective", forbidden_warp)

    result = align_page(original, template)

    assert result.image is None
    assert result.reason == "geometry_failure"


@pytest.mark.parametrize("failure_stage", ["matcher", "find", "transform", "warp"])
def test_each_opencv_geometry_failure_path_fails_safely(monkeypatch, failure_stage):
    original = _feature_page()
    template = build_sync_template(original)

    def fail(*_args, **_kwargs):
        raise cv2.error(f"{failure_stage} failure")

    if failure_stage == "matcher":
        class BrokenMatcher:
            def knnMatch(self, *_args, **_kwargs):
                return fail()

        monkeypatch.setattr(cv2, "BFMatcher", lambda *_args, **_kwargs: BrokenMatcher())
    elif failure_stage == "find":
        monkeypatch.setattr(cv2, "findHomography", fail)
    elif failure_stage == "transform":
        monkeypatch.setattr(cv2, "perspectiveTransform", fail)
    else:
        monkeypatch.setattr(cv2, "warpPerspective", fail)

    result = align_page(original, template)

    assert result.image is None
    assert result.homography is None
    assert result.reason == "geometry_failure"
