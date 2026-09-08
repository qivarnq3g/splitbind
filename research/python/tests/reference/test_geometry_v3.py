from __future__ import annotations

from dataclasses import replace

import cv2
import numpy as np
import pytest

import splitbind_ref.geometry_v3 as geometry_module
from splitbind_ref.fingerprint_v3_profile import load_v3_profiles, v2_pilot_profile
from splitbind_ref.geometry_v3 import geometry_hypotheses_v3
from splitbind_ref.synchronization import SyncTemplate
from splitbind_ref.synchronization_v2 import AlignmentV2Result


KEY = bytes(range(32))


@pytest.fixture
def profile():
    return load_v3_profiles()[0]


@pytest.fixture(autouse=True)
def disable_sync_fallback(monkeypatch):
    """Keep shape-prior tests independent of the slower V2 sync estimator."""

    monkeypatch.setattr(
        geometry_module,
        "align_page_v2",
        lambda *_args, **_kwargs: AlignmentV2Result(
            None, None, 0.0, 0, "insufficient_sync_evidence"
        ),
    )


def _checkerboard(height: int, width: int) -> np.ndarray:
    y, x = np.indices((height, width))
    values = (((x // 11) + (y // 7)) % 2 * 255).astype(np.uint8)
    return np.repeat(values[..., None], 3, axis=2)


def _center_crop(page: np.ndarray, retained_scale: float) -> np.ndarray:
    height, width = page.shape[:2]
    retained_height = round(height * retained_scale)
    retained_width = round(width * retained_scale)
    y0 = (height - retained_height) // 2
    x0 = (width - retained_width) // 2
    return page[y0 : y0 + retained_height, x0 : x0 + retained_width].copy()


def test_geometry_returns_identity_first_for_canonical_shape(profile):
    """Catches omission or reordering of the exact-shape identity prior."""

    page = np.zeros((1536, 3072, 3), np.uint8)

    hypotheses = geometry_hypotheses_v3(page, KEY, 0, page.shape[:2], profile)

    assert hypotheses[0].kind == "identity"
    np.testing.assert_array_equal(hypotheses[0].source_to_canonical, np.eye(3))
    assert len(hypotheses) <= profile.max_geometry_hypotheses


def test_geometry_pure_resize_uses_the_frozen_cubic_interpolation(profile):
    """Catches interpolation drift or stretching with the wrong target shape."""

    page = _checkerboard(96, 192)
    canonical_shape = (144, 288)
    expected = cv2.resize(page, (288, 144), interpolation=cv2.INTER_CUBIC)

    candidate = next(
        hypothesis
        for hypothesis in geometry_hypotheses_v3(
            page, KEY, 3, canonical_shape, profile
        )
        if hypothesis.kind == "pure_resize"
    )

    np.testing.assert_array_equal(candidate.image, expected)
    np.testing.assert_allclose(
        candidate.source_to_canonical,
        np.array(
            [[1.5, 0.0, 0.25], [0.0, 1.5, 0.25], [0.0, 0.0, 1.0]],
            dtype=np.float64,
        ),
    )


def test_geometry_reconstructs_center_crop_without_stretching(profile):
    """Catches a crop prior that resizes content instead of padding it in place."""

    canonical = _checkerboard(1536, 3072)
    crop = _center_crop(canonical, 0.8660254037844386)

    candidate = next(
        hypothesis
        for hypothesis in geometry_hypotheses_v3(
            crop, KEY, 0, canonical.shape[:2], profile
        )
        if hypothesis.kind == "center_crop"
    )

    y0 = (canonical.shape[0] - crop.shape[0]) // 2
    x0 = (canonical.shape[1] - crop.shape[1]) // 2
    np.testing.assert_array_equal(
        candidate.image[y0 : y0 + crop.shape[0], x0 : x0 + crop.shape[1]], crop
    )
    assert np.all(candidate.image[:y0] == 255)
    assert np.all(candidate.image[:, :x0] == 255)
    np.testing.assert_array_equal(
        candidate.source_to_canonical,
        np.array(
            [[1.0, 0.0, float(x0)], [0.0, 1.0, float(y0)], [0.0, 0.0, 1.0]],
            dtype=np.float64,
        ),
    )


def test_geometry_rejects_shape_priors_when_axis_ratios_disagree(profile):
    """Catches fabrication of resize/crop geometry for an aspect-ratio mismatch."""

    page = np.zeros((150, 301, 3), np.uint8)

    hypotheses = geometry_hypotheses_v3(page, KEY, 0, (200, 400), profile)

    assert not {"pure_resize", "center_crop"}.intersection(
        hypothesis.kind for hypothesis in hypotheses
    )


def test_geometry_rejects_over_40_megapixels_before_materializing_the_view(profile):
    """Catches an unbounded input copy or allocation before the pixel ceiling."""

    pixel = np.zeros((1, 1, 3), np.uint8)
    oversized = np.broadcast_to(pixel, (40_000_001, 1, 3))

    with pytest.raises(ValueError, match="40-megapixel"):
        geometry_hypotheses_v3(oversized, KEY, 0, (1, 1), profile)


def test_geometry_rejects_canonical_canvas_over_40_megapixels(profile):
    """Catches an unbounded canonical output allocation beyond the pixel ceiling."""

    with pytest.raises(ValueError, match="40-megapixel"):
        geometry_hypotheses_v3(
            np.zeros((1, 1, 3), np.uint8),
            KEY,
            0,
            (40_000_001, 1),
            profile,
        )


def test_geometry_places_shape_priors_before_one_valid_sync_fallback(
    profile, monkeypatch
):
    """Catches fallback-first ordering, dropped ORB input, or invented provenance."""

    page = _checkerboard(96, 192)
    canonical_shape = (144, 288)
    fallback_matrix = np.array(
        [[1.5, 0.01, 2.0], [-0.01, 1.5, -1.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    fallback_image = np.full((144, 288, 3), 17, np.uint8)
    orb_template = SyncTemplate(
        canonical_shape,
        np.array(
            [[12.0, 12.0], [275.0, 12.0], [275.0, 131.0], [12.0, 131.0]],
            dtype=np.float32,
        ),
        np.zeros((4, 32), dtype=np.uint8),
    )
    observed = {}

    def aligned(
        attacked,
        key,
        page_index,
        pilot_profile,
        canonical,
        received_orb_template=None,
    ):
        observed["arguments"] = (
            attacked,
            key,
            page_index,
            pilot_profile,
            canonical,
            received_orb_template,
        )
        return AlignmentV2Result(
            fallback_image, fallback_matrix, 0.63, 2, "aligned"
        )

    monkeypatch.setattr(geometry_module, "align_page_v2", aligned)

    hypotheses = geometry_hypotheses_v3(
        page, KEY, 7, canonical_shape, profile, orb_template=orb_template
    )

    assert [hypothesis.kind for hypothesis in hypotheses] == ["pure_resize", "sync"]
    np.testing.assert_array_equal(hypotheses[1].image, fallback_image)
    assert hypotheses[1].score == pytest.approx(0.63)
    assert observed["arguments"][0] is page
    assert observed["arguments"][1:] == (
        KEY,
        7,
        v2_pilot_profile(profile),
        canonical_shape,
        orb_template,
    )


def test_geometry_deduplicates_quantized_matrices_in_favor_of_shape_prior(
    profile, monkeypatch
):
    """Catches duplicate payload votes from numerically equivalent transforms."""

    page = _checkerboard(96, 192)
    canonical_shape = (144, 288)
    resize_matrix = np.array(
        [[1.5, 0.0, 0.25], [0.0, 1.5, 0.25], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    numerically_equivalent = resize_matrix.copy()
    numerically_equivalent[0, 2] += 1e-10
    monkeypatch.setattr(
        geometry_module,
        "align_page_v2",
        lambda *_args, **_kwargs: AlignmentV2Result(
            cv2.resize(page, (288, 144), interpolation=cv2.INTER_CUBIC),
            numerically_equivalent,
            0.75,
            1,
            "aligned",
        ),
    )

    hypotheses = geometry_hypotheses_v3(
        page, KEY, 0, canonical_shape, profile
    )

    assert [hypothesis.kind for hypothesis in hypotheses] == ["pure_resize"]
    keys = {
        tuple(np.round(hypothesis.source_to_canonical, decimals=8).flat)
        for hypothesis in hypotheses
    }
    assert len(keys) == len(hypotheses)


def test_geometry_stops_at_profile_limit_before_running_fallback(profile, monkeypatch):
    """Catches work or output beyond the profile's hard hypothesis ceiling."""

    limited_profile = replace(profile, max_geometry_hypotheses=1)

    def forbidden_fallback(*_args, **_kwargs):
        raise AssertionError("fallback must not run after the hypothesis limit")

    monkeypatch.setattr(geometry_module, "align_page_v2", forbidden_fallback)

    hypotheses = geometry_hypotheses_v3(
        np.zeros((64, 128, 3), np.uint8),
        KEY,
        0,
        (64, 128),
        limited_profile,
    )

    assert [hypothesis.kind for hypothesis in hypotheses] == ["identity"]


def test_geometry_search_does_not_invent_sync_when_limit_skips_fallback(
    profile, monkeypatch
):
    """Catches fabricated alignment evidence when shape priors fill the limit."""

    limited_profile = replace(profile, max_geometry_hypotheses=1)

    def forbidden_fallback(*_args, **_kwargs):
        raise AssertionError("fallback must not run after the hypothesis limit")

    monkeypatch.setattr(geometry_module, "align_page_v2", forbidden_fallback)

    result = geometry_module.search_geometry_v3(
        np.zeros((64, 128, 3), np.uint8),
        KEY,
        0,
        (64, 128),
        limited_profile,
    )

    assert [hypothesis.kind for hypothesis in result.hypotheses] == ["identity"]
    assert result.sync_reason is None


@pytest.mark.parametrize("reason", ["insufficient_sync_evidence", "geometry_rejected"])
def test_geometry_search_retains_observed_empty_fallback_reason(profile, monkeypatch, reason):
    monkeypatch.setattr(
        geometry_module, "align_page_v2",
        lambda *_args: AlignmentV2Result(None, None, 0.0, 1, reason),
    )
    result = geometry_module.search_geometry_v3(
        np.zeros((64, 100, 3), np.uint8), KEY, 0, (96, 192), profile
    )
    assert result.hypotheses == ()
    assert result.sync_reason == reason


def test_geometry_search_retains_shape_prior_when_fallback_rejected(profile, monkeypatch):
    monkeypatch.setattr(
        geometry_module, "align_page_v2",
        lambda *_args: AlignmentV2Result(None, None, 0.0, 1, "geometry_rejected"),
    )
    result = geometry_module.search_geometry_v3(
        np.zeros((64, 128, 3), np.uint8), KEY, 0, (64, 128), profile
    )
    assert [item.kind for item in result.hypotheses] == ["identity"]
    assert result.sync_reason == "geometry_rejected"
