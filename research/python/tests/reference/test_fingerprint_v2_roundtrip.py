"""Public V2 facade round trips over real uint8 BGR rasters."""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID

import numpy as np
import pytest

from splitbind_bench.metrics import compute_quality_metrics
from splitbind_ref.fingerprint_v2 import (
    FingerprintV2Context,
    decode_fingerprint_v2,
    embed_fingerprint_v2,
)
from splitbind_ref.fingerprint_v2_profile import load_v2_profiles


ISSUANCE_ID = UUID("12345678-1234-5678-1234-567812345678")
KEY = bytes.fromhex("00112233445566778899aabbccddeeff" * 2)
PAGE_INDEX = 0


def _gradient_page(height: int, width: int) -> np.ndarray:
    y, x = np.indices((height, width), dtype=np.float64)
    blue = 28.0 + 151.0 * x / max(1, width - 1) + 18.0 * y / max(1, height - 1)
    green = 34.0 + 139.0 * x / max(1, width - 1) + 24.0 * y / max(1, height - 1)
    red = 41.0 + 126.0 * x / max(1, width - 1) + 31.0 * y / max(1, height - 1)
    return np.ascontiguousarray(
        np.stack((blue, green, red), axis=2).clip(0, 255).astype(np.uint8)
    )


@pytest.fixture(scope="module")
def gradient_page() -> np.ndarray:
    """A featureless raster still supplies enough 384-pixel V2 tile slots."""

    return _gradient_page(1536, 2304)


@pytest.fixture(scope="module")
def all_candidate_page() -> np.ndarray:
    """The 512-pixel candidates need their contracted 3x6 tile grid."""

    return _gradient_page(1536, 3072)


@pytest.fixture(scope="module")
def profile():
    return load_v2_profiles()[0]


def test_v2_roundtrip_on_gradient_has_no_orb_dependency(gradient_page, profile):
    embedded = embed_fingerprint_v2(
        gradient_page,
        FingerprintV2Context(ISSUANCE_ID, KEY, PAGE_INDEX),
        profile,
    )

    decoded = decode_fingerprint_v2(
        embedded.image, KEY, PAGE_INDEX, gradient_page.shape[:2], (profile,)
    )

    assert decoded.status == "decoded"
    assert decoded.issuance_id == ISSUANCE_ID
    assert decoded.valid_votes >= 2
    assert embedded.embedded_repetitions == profile.payload_repetitions


@pytest.mark.parametrize("profile_index", range(16))
def test_every_v2_candidate_has_a_clean_public_roundtrip(
    all_candidate_page, profile_index
):
    profile = load_v2_profiles()[profile_index]
    embedded = embed_fingerprint_v2(
        all_candidate_page,
        FingerprintV2Context(ISSUANCE_ID, KEY, PAGE_INDEX),
        profile,
    )

    decoded = decode_fingerprint_v2(
        embedded.image, KEY, PAGE_INDEX, all_candidate_page.shape[:2], (profile,)
    )

    assert decoded.status == "decoded"
    assert decoded.issuance_id == ISSUANCE_ID
    assert decoded.valid_votes == profile.payload_repetitions


def test_v2_embedding_measures_quality_after_the_single_final_raster_replacement(
    gradient_page, profile
):
    embedded = embed_fingerprint_v2(
        gradient_page,
        FingerprintV2Context(ISSUANCE_ID, KEY, PAGE_INDEX),
        profile,
    )

    measured = compute_quality_metrics(gradient_page, embedded.image)

    assert embedded.image.dtype == np.uint8
    assert embedded.psnr_db == pytest.approx(measured.psnr_db, abs=1e-12)
    assert embedded.ssim == pytest.approx(measured.ssim, abs=1e-12)
    assert embedded.psnr_db >= 0.0
    assert 0.0 <= embedded.ssim <= 1.0


def test_embedding_and_decoding_do_not_mutate_their_uint8_inputs(gradient_page, profile):
    original = gradient_page.copy()
    embedded = embed_fingerprint_v2(
        gradient_page,
        FingerprintV2Context(ISSUANCE_ID, KEY, PAGE_INDEX),
        profile,
    )
    embedded_before_decode = embedded.image.copy()

    decode_fingerprint_v2(
        embedded.image, KEY, PAGE_INDEX, gradient_page.shape[:2], (profile,)
    )

    np.testing.assert_array_equal(gradient_page, original)
    np.testing.assert_array_equal(embedded.image, embedded_before_decode)
    assert not np.shares_memory(embedded.image, gradient_page)
    assert int(embedded.image.min()) >= 0
    assert int(embedded.image.max()) <= np.iinfo(np.uint8).max


def test_wrong_key_page_and_profile_never_attribute(gradient_page, profile):
    embedded = embed_fingerprint_v2(
        gradient_page,
        FingerprintV2Context(ISSUANCE_ID, KEY, PAGE_INDEX),
        profile,
    )
    profiles = load_v2_profiles()

    decisions = (
        decode_fingerprint_v2(
            embedded.image, b"w" * 32, PAGE_INDEX, gradient_page.shape[:2], (profile,)
        ),
        decode_fingerprint_v2(
            embedded.image, KEY, PAGE_INDEX + 1, gradient_page.shape[:2], (profile,)
        ),
        decode_fingerprint_v2(
            embedded.image, KEY, PAGE_INDEX, gradient_page.shape[:2], (profiles[4],)
        ),
    )

    assert all(decision.issuance_id is None for decision in decisions)
    assert all(decision.status != "decoded" for decision in decisions)


def test_non_decoded_clean_negative_never_exposes_an_issuance_id(gradient_page, profile):
    negative = np.zeros_like(gradient_page)

    decision = decode_fingerprint_v2(
        negative, KEY, PAGE_INDEX, gradient_page.shape[:2], (profile,)
    )

    assert decision.status == "insufficient_sync_evidence"
    assert decision.issuance_id is None


@pytest.mark.parametrize(
    "page",
    (
        np.zeros((384, 512), dtype=np.uint8),
        np.zeros((384, 512, 3), dtype=np.uint16),
        np.zeros((0, 512, 3), dtype=np.uint8),
    ),
)
def test_public_v2_facade_rejects_non_uint8_bgr_pages(page, profile):
    with pytest.raises((TypeError, ValueError)):
        embed_fingerprint_v2(
            page,
            FingerprintV2Context(ISSUANCE_ID, KEY, PAGE_INDEX),
            profile,
        )


@pytest.mark.parametrize(
    "canonical_shape",
    ((0, 2304), (1536, 0), (5000, 8001), (True, 2304)),
)
def test_decode_rejects_invalid_canonical_canvas_metadata(
    gradient_page, profile, canonical_shape
):
    with pytest.raises(ValueError, match="canonical_shape"):
        decode_fingerprint_v2(
            gradient_page, KEY, PAGE_INDEX, canonical_shape, (profile,)
        )


def test_wrong_canonical_canvas_never_attributes_or_mutates_input(gradient_page, profile):
    original = gradient_page.copy()
    embedded = embed_fingerprint_v2(
        gradient_page,
        FingerprintV2Context(ISSUANCE_ID, KEY, PAGE_INDEX),
        profile,
    )
    before_decode = embedded.image.copy()

    decision = decode_fingerprint_v2(
        embedded.image, KEY, PAGE_INDEX, (1536, 3072), (profile,)
    )

    assert decision.issuance_id is None
    assert decision.status != "decoded"
    np.testing.assert_array_equal(gradient_page, original)
    np.testing.assert_array_equal(embedded.image, before_decode)


@pytest.mark.parametrize(
    "mutated",
    (
        lambda profile: replace(profile, bit_confidence_min=0.61),
        lambda profile: replace(profile, pilot_score_min=0.21),
    ),
)
def test_decode_rejects_noncanonical_profile_before_alignment(
    gradient_page, profile, mutated, monkeypatch
):
    def forbidden_alignment(*_args, **_kwargs):
        raise AssertionError("noncanonical profiles must fail before alignment")

    monkeypatch.setattr("splitbind_ref.fingerprint_v2.align_page_v2", forbidden_alignment)

    with pytest.raises(ValueError, match="frozen V2 grid"):
        decode_fingerprint_v2(
            gradient_page,
            KEY,
            PAGE_INDEX,
            gradient_page.shape[:2],
            (mutated(profile),),
        )


def test_noncanonical_profile_is_rejected_before_page_contiguity_allocation(
    gradient_page, profile, monkeypatch
):
    noncanonical = replace(profile, bit_confidence_min=0.61)
    noncontiguous = gradient_page[:, ::2, :]

    def forbidden_contiguous_copy(*_args, **_kwargs):
        raise AssertionError("noncanonical profile reached page allocation")

    monkeypatch.setattr(
        "splitbind_ref.fingerprint_v2.np.ascontiguousarray",
        forbidden_contiguous_copy,
    )

    with pytest.raises(ValueError, match="frozen V2 grid"):
        embed_fingerprint_v2(
            noncontiguous,
            FingerprintV2Context(ISSUANCE_ID, KEY, PAGE_INDEX),
            noncanonical,
        )
    with pytest.raises(ValueError, match="frozen V2 grid"):
        decode_fingerprint_v2(
            noncontiguous,
            KEY,
            PAGE_INDEX,
            gradient_page.shape[:2],
            (noncanonical,),
        )
