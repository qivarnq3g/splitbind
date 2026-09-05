from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from splitbind_ref import contracts
from splitbind_ref.contracts import CONTRACT_ROOT_ENV
from splitbind_ref.fingerprint_v2_profile import FingerprintV2Profile
from splitbind_ref.fingerprint_v3_profile import (
    FingerprintV3Profile,
    candidate_identifier_v3,
    load_v3_profiles,
    v2_pilot_profile,
)


ROOT = Path(__file__).resolve().parents[4]
V3_PATH = ROOT / "contracts" / "algorithm" / "fingerprint-candidates.v3.json"
V3_CONTRACT_SHA256 = "14a47ced36eede7a4342c6ee280a59758747415a3b28331cfb16ab2e4f16ea23"
V3_FIRST_IDENTIFIER_HEX = (
    "534246330114a47ced36eede7a4342c6ee280a59758747415a3b28331cfb16ab2e4f16ea23000000"
    "03404000000000000040000000000000004010000000000000000000403fe8000000000000000000"
    "10000000ef000001800000001200000003000000033fe33333333333333fc999999999999a000000"
    "083f50624dd2f1a9fc000000013febb67ae8584caa0000000b494e5445525f4355424943"
)


@pytest.fixture(autouse=True)
def clear_v3_contract_cache():
    contracts._fingerprint_candidates_v3_cached.cache_clear()
    yield
    contracts._fingerprint_candidates_v3_cached.cache_clear()


def test_v3_contract_expands_a_bounded_deterministic_grid():
    """Catches a missing, unbounded, or nondeterministic V3 candidate expansion."""

    profiles = load_v3_profiles()

    assert len(profiles) == 4
    assert len({candidate_identifier_v3(profile) for profile in profiles}) == len(profiles)
    assert all(profile.schema_version == 3 for profile in profiles)
    assert all(profile.max_geometry_hypotheses == 8 for profile in profiles)


def test_v3_contract_and_first_identifier_are_golden_lf_big_endian_bytes():
    """Locks the contract digest and the complete cross-language identity layout."""

    raw = V3_PATH.read_bytes()
    assert b"\r" not in raw
    assert sha256(raw).hexdigest() == V3_CONTRACT_SHA256
    assert contracts.fingerprint_candidates_v3_bytes() == raw

    identifier = candidate_identifier_v3(load_v3_profiles()[0])
    assert len(identifier) == 156
    assert identifier.hex() == V3_FIRST_IDENTIFIER_HEX


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("contract_sha256", b"\x01" * 32),
        ("qim_delta", 33.0),
        ("pilot_strength_rms", 2.5),
        ("spread_delta", 5.0),
        ("spread_chips_per_bit", 65),
        ("saturated_fraction_min", 0.8),
        ("saturation_low", 15),
        ("saturation_high", 238),
        ("tile_size_px", 512),
        ("tiles_per_page", 19),
        ("payload_repetitions", 5),
        ("bit_replication", 4),
        ("bit_confidence_min", 0.61),
        ("pilot_score_min", 0.21),
        ("max_geometry_hypotheses", 7),
        ("geometry_ratio_tolerance", 0.002),
        ("crop_retained_scales", (0.8,)),
        ("resize_interpolation", "INTER_LINEAR"),
    ],
)
def test_v3_candidate_identity_covers_every_mutable_serialized_field(field, value):
    profile = load_v3_profiles()[0]

    assert candidate_identifier_v3(replace(profile, **{field: value})) != (
        candidate_identifier_v3(profile)
    )


def test_v3_candidate_identity_covers_spread_and_geometry_fields():
    """Catches an identity that permits distinct V3 behavior to share an ID."""

    profile = load_v3_profiles()[0]

    assert candidate_identifier_v3(replace(profile, spread_delta=profile.spread_delta + 1.0)) != (
        candidate_identifier_v3(profile)
    )
    assert candidate_identifier_v3(
        replace(profile, geometry_ratio_tolerance=profile.geometry_ratio_tolerance * 2.0)
    ) != candidate_identifier_v3(profile)


def test_v3_contract_rejects_malformed_or_out_of_domain_values(tmp_path, monkeypatch):
    """Catches parser acceptance of unsafe contract mutations."""

    malformed = V3_PATH.read_text(encoding="utf-8").replace(
        '"saturated_fraction_min": 0.75', '"saturated_fraction_min": true', 1
    )
    (tmp_path / V3_PATH.name).write_text(malformed, encoding="utf-8")
    monkeypatch.setenv(CONTRACT_ROOT_ENV, str(tmp_path))
    with pytest.raises(ValueError, match="saturated_fraction_min"):
        load_v3_profiles()


def test_v3_profile_maps_to_exactly_one_frozen_v2_pilot_profile():
    """Catches a V3 pilot fallback that does not use its matching frozen V2 profile."""

    v3_profile = load_v3_profiles()[0]

    mapped = v2_pilot_profile(v3_profile)

    assert type(mapped) is FingerprintV2Profile
    assert (
        mapped.qim_delta,
        mapped.pilot_strength_rms,
        mapped.tile_size_px,
        mapped.payload_repetitions,
    ) == (
        v3_profile.qim_delta,
        v3_profile.pilot_strength_rms,
        v3_profile.tile_size_px,
        v3_profile.payload_repetitions,
    )


def test_v3_pilot_mapping_rejects_a_profile_without_a_frozen_v2_match():
    """Catches fallback to a near-match V2 profile after the V3 contract changes."""

    profile = replace(load_v3_profiles()[0], pilot_strength_rms=2.5)

    with pytest.raises(ValueError, match="exactly one frozen V2 profile"):
        v2_pilot_profile(profile)


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda text: text.replace('"schema_version": 3,', '"schema_version": 3, "schema_version": 3,', 1), "duplicate JSON key"),
        (lambda text: text.replace('"resize_interpolation": "INTER_CUBIC"', '"unknown": 1', 1), "fixed must contain exactly"),
        (lambda text: text.replace('"crop_retained_scales": [0.8660254037844386]', '"crop_retained_scales": [NaN]', 1), "finite real number"),
        (lambda text: text.replace('"tile_size_px": [384, 512]', '"tile_size_px": []', 1), "non-empty list"),
    ],
)
def test_v3_contract_rejects_invalid_json_shape(tmp_path, monkeypatch, mutator, message):
    """Catches acceptance of duplicate keys, missing keys, NaN, or an empty grid."""

    (tmp_path / V3_PATH.name).write_text(mutator(V3_PATH.read_text(encoding="utf-8")), encoding="utf-8")
    monkeypatch.setenv(CONTRACT_ROOT_ENV, str(tmp_path))
    with pytest.raises(ValueError, match=message):
        load_v3_profiles()
