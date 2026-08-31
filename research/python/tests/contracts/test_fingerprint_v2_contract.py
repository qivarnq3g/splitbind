from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from splitbind_ref import contracts
from splitbind_ref.contracts import (
    CONTRACT_ROOT_ENV,
    fingerprint_candidates_v2,
)


ROOT = Path(__file__).resolve().parents[4]
V1_PATH = ROOT / "contracts" / "algorithm" / "fingerprint-candidates.v1.json"
V2_PATH = ROOT / "contracts" / "algorithm" / "fingerprint-candidates.v2.json"


def test_v1_contract_remains_byte_identical():
    assert sha256(V1_PATH.read_bytes()).hexdigest() == (
        "d3a8c2ec271c76a2ed424dd52fc5f2760ddd3ef2773663168bbad68e54865e9f"
    )


def test_v2_contract_loader_returns_a_defensive_copy():
    first = fingerprint_candidates_v2()
    first["fixed"]["bit_confidence_min"] = 0.0

    assert fingerprint_candidates_v2()["fixed"]["bit_confidence_min"] == 0.60


def test_v2_contract_rejects_duplicate_json_keys(tmp_path, monkeypatch):
    duplicate = V2_PATH.read_text(encoding="utf-8").replace(
        '"schema_version": 2,', '"schema_version": 2, "schema_version": 2,', 1
    )
    (tmp_path / V2_PATH.name).write_text(duplicate, encoding="utf-8")
    monkeypatch.setenv(CONTRACT_ROOT_ENV, str(tmp_path))
    contracts._fingerprint_candidates_v2_cached.cache_clear()

    with pytest.raises(ValueError, match="duplicate JSON key"):
        fingerprint_candidates_v2()


def test_v2_contract_is_the_frozen_value_set():
    assert fingerprint_candidates_v2() == {
        "schema_version": 2,
        "fixed": {
            "wavelet": "haar",
            "wavelet_level": 1,
            "detail_band": "LL",
            "transform_dtype": "float64",
            "dct_block_size": 8,
            "dct_transform": "orthonormal-dct-ii",
            "midband_pairs": [[[1, 2], [2, 1]], [[2, 3], [3, 2]]],
            "luminance": {
                "channel_order": "BGR",
                "standard": "BT.601-full-range",
                "coefficients": [0.114, 0.587, 0.299],
            },
            "padding": {
                "mode": "edge",
                "edges": ["bottom", "right"],
                "inverse_crop": "original-shape",
            },
            "raster": {
                "input_dtypes": ["uint8"],
                "rounding": "nearest-bt601-floor-ceil-combination",
                "clipping": "uint8",
            },
            "qim_rounding": "ties-to-even",
            "ecc_parity_symbols": 16,
            "interleave_depth": 8,
            "bit_replication": 3,
            "bit_confidence_min": 0.60,
            "tiles_per_page": 18,
            "payload_codeword_bytes": 39,
            "pilot_frequency_pairs": 12,
            "pilot_radius_min": 0.08,
            "pilot_radius_max": 0.18,
            "pilot_axis_clearance": 0.02,
            "pilot_pair_clearance": 0.015,
            "pilot_score_min": 0.20,
            "fft_long_edge_max": 2048,
            "max_pilot_hypotheses": 3,
            "max_orb_hypotheses": 1,
            "scale_min": 0.45,
            "scale_max": 1.60,
            "rotation_degrees_min": -8.0,
            "rotation_degrees_max": 8.0,
            "translation_fraction_max": 0.60,
        },
        "coupled_levels": [
            {"qim_delta": 24.0, "pilot_strength_rms": 1.5},
            {"qim_delta": 32.0, "pilot_strength_rms": 2.0},
            {"qim_delta": 48.0, "pilot_strength_rms": 3.0},
            {"qim_delta": 64.0, "pilot_strength_rms": 4.0},
        ],
        "sweep": {"tile_size_px": [384, 512], "payload_repetitions": [3, 5]},
    }
