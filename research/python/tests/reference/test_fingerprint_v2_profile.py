from __future__ import annotations

import json
from copy import deepcopy

import pytest

import splitbind_ref.fingerprint_v2_profile as profile_module
from splitbind_ref.contracts import fingerprint_candidates_v2
from splitbind_ref.fingerprint_v2_profile import (
    candidate_identifier_v2,
    load_v2_profiles,
)


def _contract() -> dict:
    return deepcopy(fingerprint_candidates_v2())


def _profiles_from(contract: dict, monkeypatch):
    raw = json.dumps(contract, separators=(",", ":")).encode("utf-8")
    monkeypatch.setattr(profile_module, "fingerprint_candidates_v2", lambda: contract)
    monkeypatch.setattr(
        profile_module, "fingerprint_candidates_v2_bytes", lambda: raw
    )
    return load_v2_profiles()


def test_v2_grid_expands_to_exactly_sixteen_profiles():
    profiles = load_v2_profiles()

    assert len(profiles) == 16
    assert {profile.tile_size_px for profile in profiles} == {384, 512}
    assert {profile.payload_repetitions for profile in profiles} == {3, 5}
    assert {(p.qim_delta, p.pilot_strength_rms) for p in profiles} == {
        (24.0, 1.5),
        (32.0, 2.0),
        (48.0, 3.0),
        (64.0, 4.0),
    }


def test_every_v2_tile_has_three_replica_capacity():
    for profile in load_v2_profiles():
        capacity = 2 * (profile.tile_size_px // 16) ** 2
        assert capacity >= 39 * 8 * profile.bit_replication == 936


def test_candidate_identifier_binds_exact_contract_bytes_and_profile_values():
    profile = load_v2_profiles()[0]

    assert profile.contract_sha256.hex() == (
        "e7490f80b69ef1a3289afce40ef02989c9a4d89f00b916055cbf1c4c83a97b88"
    )
    assert candidate_identifier_v2(profile).hex() == (
        "5342463201e7490f80b69ef1a3289afce40ef02989c9a4d89f00b916055cbf1c4c83a97b88"
        "0000000240380000000000003ff800000000000000000180000000120000000300000003"
    )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda contract: contract["fixed"].__setitem__(
                "bit_confidence_min", True
            ),
            "bit_confidence_min",
        ),
        (
            lambda contract: contract["fixed"].__setitem__("wavelet", "db2"),
            "wavelet",
        ),
        (
            lambda contract: contract["coupled_levels"][0].__setitem__(
                "pilot_strength_rms", 1.6
            ),
            "coupled_levels",
        ),
        (
            lambda contract: contract["sweep"].__setitem__(
                "tile_size_px", [384, 384]
            ),
            "duplicate candidate identifier",
        ),
        (
            lambda contract: contract["sweep"].__setitem__(
                "tile_size_px", [384, 512, 768]
            ),
            "at most 16",
        ),
        (
            lambda contract: contract["fixed"]["midband_pairs"].__setitem__(
                1, [[1, 2], [3, 2]]
            ),
            "overlap",
        ),
        (
            lambda contract: contract["sweep"].__setitem__(
                "tile_size_px", [128, 512]
            ),
            "capacity",
        ),
    ],
    ids=[
        "boolean-numeric",
        "unsupported-fixed",
        "uncoupled-pilot",
        "duplicate-identifiers",
        "over-grid-cap",
        "overlapping-dct-coordinates",
        "insufficient-capacity",
    ],
)
def test_v2_profile_parser_rejects_contract_mutations(mutate, message, monkeypatch):
    contract = _contract()
    mutate(contract)

    with pytest.raises(ValueError, match=message):
        _profiles_from(contract, monkeypatch)
