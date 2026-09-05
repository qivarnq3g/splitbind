"""Public V3 raster behavior on the versioned representative corpus."""

from dataclasses import replace
from pathlib import Path
from uuid import UUID

import numpy as np
import pytest

from splitbind_bench.metrics import compute_quality_metrics
from splitbind_bench.runner import _fit_canvas, iter_corpus_pages
from splitbind_ref.fingerprint_v3 import FingerprintV3Context, decode_fingerprint_v3, embed_fingerprint_v3
from splitbind_ref.fingerprint_v3_profile import load_v3_profiles

ISSUANCE_ID = UUID("12345678-1234-5678-1234-567812345678")
KEY = bytes.fromhex("00112233445566778899aabbccddeeff" * 2)
CORPUS = Path(__file__).resolve().parents[4] / "fixtures/corpus/corpus-manifest.v1.json"


@pytest.fixture(scope="module")
def profile():
    return load_v3_profiles()[0]


@pytest.mark.parametrize("fixture_id", [
    "image-clean-gradient", "image-clean-noise", "pdf-one-vector", "pdf-one-whitespace",
])
def test_v3_identity_roundtrip_on_representative_corpus(fixture_id, profile):
    raw = next(iter_corpus_pages(CORPUS, fixture_ids={fixture_id})).image
    page = _fit_canvas(raw, 3072, 1536).image
    before = page.copy()
    embedded = embed_fingerprint_v3(page, FingerprintV3Context(ISSUANCE_ID, KEY, 0), profile)
    raster_before = embedded.image.copy()
    decision = decode_fingerprint_v3(embedded.image, KEY, 0, page.shape[:2], (profile,))
    assert decision.status == "decoded"
    assert decision.issuance_id == ISSUANCE_ID
    assert decision.valid_votes >= 2
    assert embedded.embedded_repetitions == profile.payload_repetitions
    assert embedded.image.dtype == np.uint8
    measured = compute_quality_metrics(page, embedded.image)
    assert embedded.psnr_db == pytest.approx(measured.psnr_db, abs=1e-12)
    assert embedded.ssim == pytest.approx(measured.ssim, abs=1e-12)
    np.testing.assert_array_equal(page, before)
    np.testing.assert_array_equal(embedded.image, raster_before)
    assert not np.shares_memory(page, embedded.image)


@pytest.mark.parametrize("profile", load_v3_profiles())
@pytest.mark.parametrize("level", [0, 255])
def test_saturated_pages_decode_without_orb(profile, level):
    page = np.full((1536, 3072, 3), level, np.uint8)
    embedded = embed_fingerprint_v3(page, FingerprintV3Context(ISSUANCE_ID, KEY, 0), profile)
    # Some pilot/payload patterns themselves create ORB points on a flat source.
    # This profile/white raster has observed insufficient post-embed features.
    if profile == load_v3_profiles()[0] and level == 255:
        assert embedded.sync_template is None
    decision = decode_fingerprint_v3(embedded.image, KEY, 0, page.shape[:2], (profile,))
    assert decision.status == "decoded"
    assert decision.issuance_id == ISSUANCE_ID
    assert decision.valid_votes == profile.payload_repetitions


def test_wrong_key_page_candidate_and_negative_never_attribute(profile):
    page = np.full((1536, 3072, 3), 255, np.uint8)
    embedded = embed_fingerprint_v3(page, FingerprintV3Context(ISSUANCE_ID, KEY, 0), profile)
    cases = ((embedded.image, b"wrong", 0, profile),
             (embedded.image, KEY, 1, profile),
             (embedded.image, KEY, 0, load_v3_profiles()[1]),
             (page, KEY, 0, profile))
    for image, key, page_index, candidate in cases:
        decision = decode_fingerprint_v3(image, key, page_index, page.shape[:2], (candidate,))
        assert decision.issuance_id is None
        assert decision.status != "decoded"


def test_noncanonical_and_unbounded_candidates_are_rejected(profile):
    page = np.zeros((384, 384, 3), np.uint8)
    with pytest.raises(ValueError, match="frozen V3 grid"):
        embed_fingerprint_v3(page, FingerprintV3Context(ISSUANCE_ID, KEY, 0), replace(profile, spread_delta=5.0))
    with pytest.raises(ValueError, match="duplicate candidate"):
        decode_fingerprint_v3(page, KEY, 0, page.shape[:2], (profile, profile))
    from itertools import repeat
    with pytest.raises(ValueError, match="at most 16"):
        decode_fingerprint_v3(page, KEY, 0, page.shape[:2], repeat(profile))


@pytest.mark.parametrize("shape", [(0, 3072), (1536, True), (5000, 8001)])
def test_invalid_canonical_shape_is_rejected(profile, shape):
    with pytest.raises(ValueError, match="canonical_shape"):
        decode_fingerprint_v3(np.zeros((1, 1, 3), np.uint8), KEY, 0, shape, (profile,))
