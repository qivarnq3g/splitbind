import numpy as np
import pytest

from splitbind_ref.synchronization import align_page, build_sync_template


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
