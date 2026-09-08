"""Fail-closed V3 quorum behavior and representative real attacks."""

from uuid import UUID
from pathlib import Path

import numpy as np
import pytest

import splitbind_ref.fingerprint_v3 as facade
from splitbind_attack.attacks import AttackCase, apply_attack
from splitbind_bench.runner import _fit_canvas, iter_corpus_pages
from splitbind_ref.fingerprint_v3_profile import candidate_identifier_v3, load_v3_profiles

ISSUANCE_ID = UUID("12345678-1234-5678-1234-567812345678")
OTHER_ID = UUID("87654321-4321-8765-4321-876543218765")
KEY = bytes.fromhex("00112233445566778899aabbccddeeff" * 2)
IDENTITY = tuple(float(v) for v in np.eye(3).flat)


@pytest.fixture(scope="module", params=["image-clean-gradient", "pdf-one-whitespace"])
def embedded_page(request):
    corpus = Path(__file__).resolve().parents[4] / "fixtures/corpus/corpus-manifest.v1.json"
    raw = next(iter_corpus_pages(corpus, fixture_ids={request.param})).image
    page = _fit_canvas(raw, 3072, 1536).image
    return facade.embed_fingerprint_v3(page, facade.FingerprintV3Context(ISSUANCE_ID, KEY, 0), load_v3_profiles()[0])


@pytest.mark.parametrize("attack", [
    AttackCase("jpeg-q70", "jpeg", {"quality": 70}),
    AttackCase("resize-s0p75", "resize", {"scale": 0.75}),
    AttackCase("crop-f0p25", "crop", {"fraction": 0.25}),
])
def test_v3_representative_attack_decodes(embedded_page, attack):
    artifact = apply_attack(embedded_page.image, attack, np.random.default_rng(20260905))
    before = artifact.image.copy()
    decision = facade.decode_fingerprint_v3(
        artifact.image, KEY, 0, embedded_page.image.shape[:2], (load_v3_profiles()[0],)
    )
    assert decision.status == "decoded"
    assert decision.issuance_id == ISSUANCE_ID
    assert decision.valid_votes >= 2
    np.testing.assert_array_equal(artifact.image, before)


def _vote(profile, ordinal, issuance=ISSUANCE_ID, codec="dct", matrix=IDENTITY):
    return facade._PayloadVoteV3(candidate_identifier_v3(profile), matrix, ordinal, codec, issuance, 0.0)


def test_duplicate_codecs_and_geometry_cannot_create_a_second_tile_vote():
    profile = load_v3_profiles()[0]
    votes = [_vote(profile, 0), _vote(profile, 0, codec="spread_darken"),
             _vote(profile, 0, matrix=tuple(float(v) for v in (np.eye(3) * 2).flat))]
    decision = facade._decide_payload_votes(votes, (profile,), 1.0)
    assert decision.status == "partial_payload_evidence"
    assert decision.issuance_id is None
    assert decision.valid_votes == 1


@pytest.mark.parametrize("conflict", ["codec", "geometry", "tile", "candidate"])
def test_any_conflicting_valid_uuid_fails_closed_even_against_quorum(conflict):
    profile, second = load_v3_profiles()[:2]
    votes = [_vote(profile, i) for i in range(3)]
    votes.append(_vote(second if conflict == "candidate" else profile,
                       1 if conflict == "tile" else 0, OTHER_ID,
                       codec="spread_lighten" if conflict == "codec" else "dct",
                       matrix=tuple(float(v) for v in (np.eye(3) * 2).flat) if conflict == "geometry" else IDENTITY))
    decision = facade._decide_payload_votes(votes, (profile, second), 1.0)
    assert decision.status == "conflicting_payload_evidence"
    assert decision.issuance_id is None


def test_quorum_is_candidate_local_and_requires_sixty_percent_support():
    first, second = load_v3_profiles()[:2]
    for votes, expected_votes in [([_vote(first, 0), _vote(second, 1)], 1),
                                  ([_vote(second, 0), _vote(second, 1)], 2)]:
        decision = facade._decide_payload_votes(votes, (first, second), 1.0)
        assert decision.status == "partial_payload_evidence"
        assert decision.issuance_id is None
        assert decision.valid_votes == expected_votes
    decision = facade._decide_payload_votes([_vote(second, i) for i in range(3)], (second,), 1.0)
    assert decision.status == "decoded"
    assert decision.confidence == 0.6
    assert decision.valid_votes == 3


@pytest.mark.parametrize("reason", ["insufficient_sync_evidence", "geometry_rejected"])
def test_empty_geometry_maps_only_the_observed_reason(monkeypatch, reason):
    import splitbind_ref.geometry_v3 as geometry
    from splitbind_ref.synchronization_v2 import AlignmentV2Result
    monkeypatch.setattr(geometry, "align_page_v2", lambda *_args: AlignmentV2Result(None, None, 0.0, 1, reason))
    page = np.zeros((64, 100, 3), np.uint8)
    decision = facade.decode_fingerprint_v3(page, KEY, 0, (96, 192), (load_v3_profiles()[0],))
    assert decision.status == reason
    assert decision.issuance_id is None


def test_geometry_runtime_failure_propagates(monkeypatch):
    import splitbind_ref.geometry_v3 as geometry
    from splitbind_ref.synchronization_v2 import AlignmentV2RuntimeError
    def failed(*_args):
        raise AlignmentV2RuntimeError("canonical_warp", 1)
    monkeypatch.setattr(geometry, "align_page_v2", failed)
    page = np.zeros((64, 100, 3), np.uint8)
    with pytest.raises(AlignmentV2RuntimeError):
        facade.decode_fingerprint_v3(page, KEY, 0, (96, 192), (load_v3_profiles()[0],))
