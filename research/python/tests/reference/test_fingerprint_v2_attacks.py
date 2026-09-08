"""V2 facade attack, evidence, and fail-closed decision tests."""

from __future__ import annotations

from collections import Counter
from uuid import UUID

import numpy as np
import pytest

import splitbind_ref.fingerprint_v2 as fingerprint_v2
from splitbind_attack.attacks import AttackCase, apply_attack
from splitbind_ref.ecc import encode_ecc
from splitbind_ref.fingerprint_v2 import (
    FingerprintV2Context,
    decode_fingerprint_v2,
    embed_fingerprint_v2,
)
from splitbind_ref.fingerprint_v2_codec import CodewordEvidence
from splitbind_ref.fingerprint_v2_profile import load_v2_profiles
from splitbind_ref.payload import encode_payload
from splitbind_ref.synchronization_v2 import (
    AlignmentV2Result,
    AlignmentV2RuntimeError,
)


ISSUANCE_ID = UUID("12345678-1234-5678-1234-567812345678")
OTHER_ISSUANCE_ID = UUID("87654321-4321-8765-4321-876543218765")
KEY = bytes.fromhex("00112233445566778899aabbccddeeff" * 2)
PAGE_INDEX = 0


def _gradient_page() -> np.ndarray:
    height, width = 1536, 2304
    y, x = np.indices((height, width), dtype=np.float64)
    return np.stack(
        (
            30.0 + 148.0 * x / (width - 1) + 16.0 * y / (height - 1),
            39.0 + 131.0 * x / (width - 1) + 21.0 * y / (height - 1),
            47.0 + 117.0 * x / (width - 1) + 27.0 * y / (height - 1),
        ),
        axis=2,
    ).clip(0, 255).astype(np.uint8)


@pytest.fixture(scope="module")
def profile():
    return load_v2_profiles()[0]


@pytest.fixture(scope="module")
def embedded_gradient(profile):
    return embed_fingerprint_v2(
        _gradient_page(),
        FingerprintV2Context(ISSUANCE_ID, KEY, PAGE_INDEX),
        profile,
    )


@pytest.mark.parametrize(
    "attack",
    (
        AttackCase("jpeg-70", "jpeg", {"quality": 70}),
        AttackCase("resize-075", "resize", {"scale": 0.75}),
        AttackCase("crop-025", "crop", {"fraction": 0.25}),
    ),
)
def test_real_v2_attack_paths_never_make_a_false_attribution(
    embedded_gradient, profile, attack
):
    artifact = apply_attack(embedded_gradient.image, attack, np.random.default_rng(20260831))

    decision = decode_fingerprint_v2(
        artifact.image,
        KEY,
        PAGE_INDEX,
        embedded_gradient.image.shape[:2],
        (profile,),
    )

    assert decision.status == "decoded"
    assert decision.issuance_id == ISSUANCE_ID
    assert decision.valid_votes >= 2


def _identity_alignment(page, *_args, **_kwargs):
    return AlignmentV2Result(
        image=page.copy(),
        homography=np.eye(3, dtype=np.float64),
        pilot_score=1.0,
        hypothesis_count=1,
        reason="aligned",
    )


def test_aligned_negative_with_no_crc_valid_payload_is_not_detected(profile, monkeypatch):
    monkeypatch.setattr(fingerprint_v2, "align_page_v2", _identity_alignment)
    page = _gradient_page()

    decision = decode_fingerprint_v2(
        page, KEY, PAGE_INDEX, page.shape[:2], (profile,)
    )

    assert decision == fingerprint_v2.DecodeV2Decision(
        issuance_id=None,
        confidence=1.0,
        valid_votes=0,
        bit_error_rate=None,
        status="payload_not_detected",
    )


def test_one_crc_valid_tile_is_partial_payload_evidence(profile, monkeypatch):
    valid_codeword = encode_ecc(encode_payload(ISSUANCE_ID))
    calls = 0
    monkeypatch.setattr(fingerprint_v2, "align_page_v2", _identity_alignment)

    def extract_one_valid(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return CodewordEvidence(
            codeword=valid_codeword if calls == 1 else bytes(39),
            erase_positions=(),
            mean_confidence=0.8,
            bit_error_hint=0.1,
        )

    monkeypatch.setattr(fingerprint_v2, "extract_codeword_v2", extract_one_valid)

    page = _gradient_page()
    decision = decode_fingerprint_v2(
        page, KEY, PAGE_INDEX, page.shape[:2], (profile,)
    )

    assert decision.status == "partial_payload_evidence"
    assert decision.issuance_id is None
    assert decision.valid_votes == 1


def test_conflicting_candidate_local_quorums_fail_closed(monkeypatch):
    first, second = load_v2_profiles()[0], load_v2_profiles()[4]
    first_codeword = encode_ecc(encode_payload(ISSUANCE_ID))
    second_codeword = encode_ecc(encode_payload(OTHER_ISSUANCE_ID))
    monkeypatch.setattr(fingerprint_v2, "align_page_v2", _identity_alignment)

    def extract_conflicting(_tile, _key, _page_index, profile):
        codeword = first_codeword if profile == first else second_codeword
        return CodewordEvidence(codeword, (), 0.8, 0.1)

    monkeypatch.setattr(fingerprint_v2, "extract_codeword_v2", extract_conflicting)

    page = _gradient_page()
    decision = decode_fingerprint_v2(
        page, KEY, PAGE_INDEX, page.shape[:2], (first, second)
    )

    assert decision.status == "partial_payload_evidence"
    assert decision.issuance_id is None
    assert decision.valid_votes == first.payload_repetitions


def test_geometry_rejection_is_the_only_safety_rejection_status(profile, monkeypatch):
    def rejected(*_args, **_kwargs):
        return AlignmentV2Result(None, None, 0.23, 2, "geometry_rejected")

    monkeypatch.setattr(fingerprint_v2, "align_page_v2", rejected)

    page = _gradient_page()
    decision = decode_fingerprint_v2(
        page, KEY, PAGE_INDEX, page.shape[:2], (profile,)
    )

    assert decision.status == "geometry_rejected"
    assert decision.issuance_id is None
    assert decision.valid_votes == 0


def test_alignment_runtime_errors_propagate_for_execution_error_mapping(profile, monkeypatch):
    def runtime_failure(*_args, **_kwargs):
        raise AlignmentV2RuntimeError("canonical_warp", 1)

    monkeypatch.setattr(fingerprint_v2, "align_page_v2", runtime_failure)

    with pytest.raises(AlignmentV2RuntimeError, match="canonical_warp"):
        page = _gradient_page()
        decode_fingerprint_v2(page, KEY, PAGE_INDEX, page.shape[:2], (profile,))


def test_decoder_aligns_once_per_unique_candidate_and_honors_repetition_cap(
    profile, monkeypatch
):
    second = load_v2_profiles()[4]
    alignments: list[object] = []
    extractions: Counter[object] = Counter()

    def record_alignment(page, _key, _page_index, candidate, canonical_shape):
        alignments.append(candidate)
        return _identity_alignment(page)

    def record_extraction(_tile, _key, _page_index, candidate):
        extractions[candidate] += 1
        return CodewordEvidence(bytes(39), (), 0.7, 0.2)

    monkeypatch.setattr(fingerprint_v2, "align_page_v2", record_alignment)
    monkeypatch.setattr(fingerprint_v2, "extract_codeword_v2", record_extraction)

    page = _gradient_page()
    decision = decode_fingerprint_v2(
        page, KEY, PAGE_INDEX, page.shape[:2], (profile, second)
    )

    assert decision.status == "payload_not_detected"
    assert alignments == [profile, second]
    assert extractions == Counter(
        {profile: profile.payload_repetitions, second: second.payload_repetitions}
    )


def test_decoder_rejects_duplicate_or_more_than_sixteen_profiles(profile):
    page = np.zeros((384, 512, 3), dtype=np.uint8)

    with pytest.raises(ValueError, match="duplicate candidate"):
        decode_fingerprint_v2(page, KEY, PAGE_INDEX, page.shape[:2], (profile, profile))
    with pytest.raises(ValueError, match="at most 16"):
        decode_fingerprint_v2(
            page, KEY, PAGE_INDEX, page.shape[:2], (*load_v2_profiles(), profile)
        )


def test_conflicting_crc_valid_votes_within_one_candidate_fail_closed(profile, monkeypatch):
    codewords = (
        encode_ecc(encode_payload(ISSUANCE_ID)),
        encode_ecc(encode_payload(ISSUANCE_ID)),
        encode_ecc(encode_payload(OTHER_ISSUANCE_ID)),
    )
    calls = 0
    monkeypatch.setattr(fingerprint_v2, "align_page_v2", _identity_alignment)

    def extract_conflict_within_candidate(*_args, **_kwargs):
        nonlocal calls
        codeword = codewords[calls]
        calls += 1
        return CodewordEvidence(codeword, (), 0.8, 0.1)

    monkeypatch.setattr(
        fingerprint_v2, "extract_codeword_v2", extract_conflict_within_candidate
    )
    page = _gradient_page()

    decision = decode_fingerprint_v2(
        page, KEY, PAGE_INDEX, page.shape[:2], (profile,)
    )

    assert decision.status == "partial_payload_evidence"
    assert decision.issuance_id is None
    assert decision.valid_votes == 2


def test_minority_conflict_across_candidates_fails_closed(monkeypatch):
    first, second = load_v2_profiles()[0], load_v2_profiles()[4]
    first_codeword = encode_ecc(encode_payload(ISSUANCE_ID))
    second_codeword = encode_ecc(encode_payload(OTHER_ISSUANCE_ID))
    calls: Counter[object] = Counter()
    monkeypatch.setattr(fingerprint_v2, "align_page_v2", _identity_alignment)

    def extract_minority_conflict(_tile, _key, _page_index, profile):
        calls[profile] += 1
        if profile == first:
            return CodewordEvidence(first_codeword, (), 0.8, 0.1)
        if calls[profile] == 1:
            return CodewordEvidence(second_codeword, (), 0.8, 0.1)
        return CodewordEvidence(bytes(39), (), 0.8, 0.1)

    monkeypatch.setattr(fingerprint_v2, "extract_codeword_v2", extract_minority_conflict)
    page = _gradient_page()

    decision = decode_fingerprint_v2(
        page, KEY, PAGE_INDEX, page.shape[:2], (first, second)
    )

    assert decision.status == "partial_payload_evidence"
    assert decision.issuance_id is None
    assert decision.valid_votes == first.payload_repetitions


def test_decoder_bounded_infinite_profile_iterator_stops_after_seventeen_values(profile):
    page = np.zeros((384, 512, 3), dtype=np.uint8)
    yielded = 0

    def infinite_profiles():
        nonlocal yielded
        while True:
            yielded += 1
            yield profile

    with pytest.raises(ValueError, match="at most 16"):
        decode_fingerprint_v2(page, KEY, PAGE_INDEX, page.shape[:2], infinite_profiles())
    assert yielded == 17


def test_exact_full_canonical_grid_aligns_once_and_keeps_votes_candidate_local(
    monkeypatch,
):
    profiles = load_v2_profiles()
    codeword = encode_ecc(encode_payload(ISSUANCE_ID))
    aligned: list[object] = []

    def record_alignment(page, _key, _page_index, profile, canonical_shape):
        aligned.append(profile)
        return _identity_alignment(page)

    def only_first_candidate_votes(_tile, _key, _page_index, profile):
        payload = codeword if profile == profiles[0] else bytes(39)
        return CodewordEvidence(payload, (), 0.8, 0.1)

    monkeypatch.setattr(fingerprint_v2, "align_page_v2", record_alignment)
    monkeypatch.setattr(
        fingerprint_v2, "extract_codeword_v2", only_first_candidate_votes
    )
    page = np.zeros((1536, 3072, 3), dtype=np.uint8)

    decision = decode_fingerprint_v2(
        page, KEY, PAGE_INDEX, page.shape[:2], profiles
    )

    assert decision.status == "decoded"
    assert decision.issuance_id == ISSUANCE_ID
    assert decision.valid_votes == profiles[0].payload_repetitions
    assert aligned == list(profiles)
