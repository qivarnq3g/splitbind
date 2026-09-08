"""Strict parsing and candidate identities for the frozen V2 research grid."""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from hashlib import sha256
from itertools import product
from typing import Any

from .contracts import fingerprint_candidates_v2, fingerprint_candidates_v2_bytes


_EXPECTED_FIXED = {
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
}
_EXPECTED_COUPLED_LEVELS = (
    (24.0, 1.5),
    (32.0, 2.0),
    (48.0, 3.0),
    (64.0, 4.0),
)
_EXPECTED_TILE_SIZES = (384, 512)
_EXPECTED_REPETITIONS = (3, 5)


@dataclass(frozen=True, slots=True)
class FingerprintV2Profile:
    schema_version: int
    contract_sha256: bytes
    qim_delta: float
    pilot_strength_rms: float
    tile_size_px: int
    tiles_per_page: int
    payload_repetitions: int
    bit_replication: int
    bit_confidence_min: float
    pilot_score_min: float


def load_v2_profiles() -> tuple[FingerprintV2Profile, ...]:
    """Parse, validate, and expand the frozen V2 candidate grid."""

    contract = fingerprint_candidates_v2()
    raw = fingerprint_candidates_v2_bytes()
    _require_object(contract, "contract")
    _require_exact_keys(contract, {"schema_version", "fixed", "coupled_levels", "sweep"}, "contract")
    schema_version = _require_integer(contract["schema_version"], "schema_version")
    if schema_version != 2:
        raise ValueError("schema_version must be 2")

    fixed = _validate_fixed(contract["fixed"])
    coupled_levels = _validate_coupled_levels(contract["coupled_levels"])
    tile_sizes, repetitions = _validate_sweep(contract["sweep"])

    expanded_count = len(coupled_levels) * len(tile_sizes) * len(repetitions)
    if expanded_count > 16:
        raise ValueError("V2 candidate grid must contain at most 16 profiles")
    if expanded_count == 0:
        raise ValueError("V2 candidate grid must not be empty")

    required_bits = _require_integer(fixed["payload_codeword_bytes"], "payload_codeword_bytes") * 8
    required_bits *= _require_integer(fixed["bit_replication"], "bit_replication")
    for tile_size_px in tile_sizes:
        capacity = 2 * (tile_size_px // 16) ** 2
        if capacity < required_bits:
            raise ValueError(
                f"tile_size_px {tile_size_px} has insufficient capacity "
                f"({capacity} < {required_bits})"
            )

    contract_sha256 = sha256(raw).digest()
    profiles = tuple(
        FingerprintV2Profile(
            schema_version=schema_version,
            contract_sha256=contract_sha256,
            qim_delta=qim_delta,
            pilot_strength_rms=pilot_strength_rms,
            tile_size_px=tile_size_px,
            tiles_per_page=fixed["tiles_per_page"],
            payload_repetitions=payload_repetitions,
            bit_replication=fixed["bit_replication"],
            bit_confidence_min=fixed["bit_confidence_min"],
            pilot_score_min=fixed["pilot_score_min"],
        )
        for (qim_delta, pilot_strength_rms), tile_size_px, payload_repetitions in product(
            coupled_levels, tile_sizes, repetitions
        )
    )
    identifiers = [candidate_identifier_v2(profile) for profile in profiles]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("duplicate candidate identifier in V2 candidate grid")

    if coupled_levels != _EXPECTED_COUPLED_LEVELS:
        raise ValueError("coupled_levels must use the frozen V2 QIM/pilot pairs")
    if tile_sizes != _EXPECTED_TILE_SIZES or repetitions != _EXPECTED_REPETITIONS:
        raise ValueError("sweep must use the frozen V2 tile sizes and repetitions")
    return profiles


def candidate_identifier_v2(profile: FingerprintV2Profile) -> bytes:
    """Return the fixed cross-language binary identity for one V2 candidate."""

    if not isinstance(profile, FingerprintV2Profile):
        raise TypeError("profile must be a FingerprintV2Profile")
    if len(profile.contract_sha256) != 32:
        raise ValueError("profile contract_sha256 must contain exactly 32 bytes")
    return (
        b"SBF2\x01"
        + profile.contract_sha256
        + struct.pack(
            ">IddIIII",
            profile.schema_version,
            profile.qim_delta,
            profile.pilot_strength_rms,
            profile.tile_size_px,
            profile.tiles_per_page,
            profile.payload_repetitions,
            profile.bit_replication,
        )
    )


def _validate_fixed(value: Any) -> dict[str, Any]:
    fixed = _require_object(value, "fixed")
    _require_exact_keys(fixed, set(_EXPECTED_FIXED), "fixed")
    _validate_midband_pairs(fixed["midband_pairs"])
    _validate_luminance(fixed["luminance"])
    _validate_padding(fixed["padding"])
    _validate_raster(fixed["raster"])

    for field, expected in _EXPECTED_FIXED.items():
        actual = fixed[field]
        if isinstance(expected, int):
            _require_integer(actual, field)
        elif isinstance(expected, float):
            _require_real(actual, field)
        if actual != expected:
            raise ValueError(f"fixed.{field} is not supported by V2")
    return fixed


def _validate_midband_pairs(value: Any) -> None:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("fixed.midband_pairs must contain exactly two coefficient pairs")
    coordinates: set[tuple[int, int]] = set()
    for pair in value:
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError("fixed.midband_pairs must contain coordinate pairs")
        for coordinate in pair:
            if not isinstance(coordinate, list) or len(coordinate) != 2:
                raise ValueError("fixed.midband_pairs must contain two-dimensional coordinates")
            parsed = tuple(_require_integer(component, "fixed.midband_pairs") for component in coordinate)
            if any(component < 0 or component >= 8 for component in parsed):
                raise ValueError("fixed.midband_pairs coordinates must be inside the DCT block")
            if parsed in coordinates:
                raise ValueError("fixed.midband_pairs coordinates must not overlap")
            coordinates.add(parsed)


def _validate_luminance(value: Any) -> None:
    luminance = _require_object(value, "fixed.luminance")
    _require_exact_keys(luminance, set(_EXPECTED_FIXED["luminance"]), "fixed.luminance")
    coefficients = luminance["coefficients"]
    if not isinstance(coefficients, list) or len(coefficients) != 3:
        raise ValueError("fixed.luminance.coefficients must have three values")
    for coefficient in coefficients:
        _require_real(coefficient, "fixed.luminance.coefficients")


def _validate_padding(value: Any) -> None:
    padding = _require_object(value, "fixed.padding")
    _require_exact_keys(padding, set(_EXPECTED_FIXED["padding"]), "fixed.padding")


def _validate_raster(value: Any) -> None:
    raster = _require_object(value, "fixed.raster")
    _require_exact_keys(raster, set(_EXPECTED_FIXED["raster"]), "fixed.raster")


def _validate_coupled_levels(value: Any) -> tuple[tuple[float, float], ...]:
    if not isinstance(value, list) or len(value) != 4:
        raise ValueError("coupled_levels must contain exactly four levels")
    levels = []
    for level in value:
        parsed = _require_object(level, "coupled_levels entry")
        _require_exact_keys(parsed, {"qim_delta", "pilot_strength_rms"}, "coupled_levels entry")
        qim_delta = _require_real(parsed["qim_delta"], "coupled_levels.qim_delta")
        pilot_strength_rms = _require_real(
            parsed["pilot_strength_rms"], "coupled_levels.pilot_strength_rms"
        )
        if qim_delta <= 0.0 or pilot_strength_rms <= 0.0:
            raise ValueError("coupled_levels values must be positive")
        levels.append((qim_delta, pilot_strength_rms))
    return tuple(levels)


def _validate_sweep(value: Any) -> tuple[tuple[int, ...], tuple[int, ...]]:
    sweep = _require_object(value, "sweep")
    _require_exact_keys(sweep, {"tile_size_px", "payload_repetitions"}, "sweep")
    tile_sizes = _require_integer_list(sweep["tile_size_px"], "sweep.tile_size_px")
    repetitions = _require_integer_list(
        sweep["payload_repetitions"], "sweep.payload_repetitions"
    )
    if any(tile_size <= 0 or tile_size % 16 != 0 for tile_size in tile_sizes):
        raise ValueError("sweep.tile_size_px must contain positive multiples of 16")
    if any(repetition <= 0 for repetition in repetitions):
        raise ValueError("sweep.payload_repetitions must contain positive values")
    return tile_sizes, repetitions


def _require_exact_keys(value: dict[str, Any], expected: set[str], name: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{name} must contain exactly {sorted(expected)}")


def _require_object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _require_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an integer, not a boolean")
    return value


def _require_real(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite real number, not a boolean")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite real number")
    return result


def _require_integer_list(value: Any, name: str) -> tuple[int, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{name} must be a non-empty list of integers")
    return tuple(_require_integer(item, name) for item in value)
