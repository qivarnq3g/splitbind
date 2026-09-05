"""Strict parsing and candidate identities for the frozen V3 research grid."""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from hashlib import sha256
from itertools import product
from typing import Any

from .contracts import fingerprint_candidates_v3, fingerprint_candidates_v3_bytes
from .fingerprint_v2_profile import FingerprintV2Profile, load_v2_profiles


_EXPECTED_FIXED = {
    "qim_delta": 32.0,
    "pilot_strength_rms": 2.0,
    "spread_delta": 4.0,
    "spread_chips_per_bit": 64,
    "saturated_fraction_min": 0.75,
    "saturation_low": 16,
    "saturation_high": 239,
    "tiles_per_page": 18,
    "bit_replication": 3,
    "bit_confidence_min": 0.60,
    "pilot_score_min": 0.20,
    "max_geometry_hypotheses": 8,
    "geometry_ratio_tolerance": 0.001,
    "crop_retained_scales": [0.8660254037844386],
    "resize_interpolation": "INTER_CUBIC",
}
_EXPECTED_TILE_SIZES = (384, 512)
_EXPECTED_REPETITIONS = (3, 5)


@dataclass(frozen=True, slots=True)
class FingerprintV3Profile:
    schema_version: int
    contract_sha256: bytes
    qim_delta: float
    pilot_strength_rms: float
    spread_delta: float
    spread_chips_per_bit: int
    saturated_fraction_min: float
    saturation_low: int
    saturation_high: int
    tile_size_px: int
    tiles_per_page: int
    payload_repetitions: int
    bit_replication: int
    bit_confidence_min: float
    pilot_score_min: float
    max_geometry_hypotheses: int
    geometry_ratio_tolerance: float
    crop_retained_scales: tuple[float, ...]
    resize_interpolation: str


def load_v3_profiles() -> tuple[FingerprintV3Profile, ...]:
    """Parse, validate, and expand the frozen V3 candidate grid."""

    contract = fingerprint_candidates_v3()
    raw = fingerprint_candidates_v3_bytes()
    _require_object(contract, "contract")
    _require_exact_keys(contract, {"schema_version", "fixed", "sweep"}, "contract")
    schema_version = _require_integer(contract["schema_version"], "schema_version")
    if schema_version != 3:
        raise ValueError("schema_version must be 3")

    fixed = _validate_fixed(contract["fixed"])
    tile_sizes, repetitions = _validate_sweep(contract["sweep"])
    expanded_count = len(tile_sizes) * len(repetitions)
    if expanded_count == 0:
        raise ValueError("V3 candidate grid must not be empty")
    if expanded_count > 16:
        raise ValueError("V3 candidate grid must contain at most 16 profiles")

    if tile_sizes != _EXPECTED_TILE_SIZES or repetitions != _EXPECTED_REPETITIONS:
        raise ValueError("sweep must use the frozen V3 tile sizes and repetitions")

    if b"\r" in raw:
        raise ValueError("V3 fingerprint candidate contract must use LF line endings")
    contract_sha256 = sha256(raw).digest()
    profiles = tuple(
        FingerprintV3Profile(
            schema_version=schema_version,
            contract_sha256=contract_sha256,
            qim_delta=_require_real(fixed["qim_delta"], "fixed.qim_delta"),
            pilot_strength_rms=_require_real(
                fixed["pilot_strength_rms"], "fixed.pilot_strength_rms"
            ),
            spread_delta=_require_real(fixed["spread_delta"], "fixed.spread_delta"),
            spread_chips_per_bit=_require_integer(
                fixed["spread_chips_per_bit"], "fixed.spread_chips_per_bit"
            ),
            saturated_fraction_min=_require_real(
                fixed["saturated_fraction_min"], "fixed.saturated_fraction_min"
            ),
            saturation_low=_require_integer(fixed["saturation_low"], "fixed.saturation_low"),
            saturation_high=_require_integer(fixed["saturation_high"], "fixed.saturation_high"),
            tile_size_px=tile_size_px,
            tiles_per_page=_require_integer(fixed["tiles_per_page"], "fixed.tiles_per_page"),
            payload_repetitions=payload_repetitions,
            bit_replication=_require_integer(fixed["bit_replication"], "fixed.bit_replication"),
            bit_confidence_min=_require_real(
                fixed["bit_confidence_min"], "fixed.bit_confidence_min"
            ),
            pilot_score_min=_require_real(fixed["pilot_score_min"], "fixed.pilot_score_min"),
            max_geometry_hypotheses=_require_integer(
                fixed["max_geometry_hypotheses"], "fixed.max_geometry_hypotheses"
            ),
            geometry_ratio_tolerance=_require_real(
                fixed["geometry_ratio_tolerance"], "fixed.geometry_ratio_tolerance"
            ),
            crop_retained_scales=_validate_crop_retained_scales(
                fixed["crop_retained_scales"]
            ),
            resize_interpolation=_require_string(
                fixed["resize_interpolation"], "fixed.resize_interpolation"
            ),
        )
        for tile_size_px, payload_repetitions in product(tile_sizes, repetitions)
    )
    identifiers = [candidate_identifier_v3(profile) for profile in profiles]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("duplicate candidate identifier in V3 candidate grid")
    return profiles


def candidate_identifier_v3(profile: FingerprintV3Profile) -> bytes:
    """Return the fixed cross-language binary identity for one V3 candidate."""

    _validate_profile(profile)
    interpolation = profile.resize_interpolation.encode("utf-8")
    return (
        b"SBF3\x01"
        + profile.contract_sha256
        + struct.pack(
            ">I", profile.schema_version
        )
        + struct.pack(
            ">d", profile.qim_delta
        )
        + struct.pack(
            ">d", profile.pilot_strength_rms
        )
        + struct.pack(
            ">d", profile.spread_delta
        )
        + struct.pack(
            ">I", profile.spread_chips_per_bit
        )
        + struct.pack(
            ">d", profile.saturated_fraction_min
        )
        + struct.pack(
            ">I", profile.saturation_low
        )
        + struct.pack(
            ">I", profile.saturation_high
        )
        + struct.pack(
            ">I", profile.tile_size_px
        )
        + struct.pack(
            ">I", profile.tiles_per_page
        )
        + struct.pack(
            ">I", profile.payload_repetitions
        )
        + struct.pack(
            ">I", profile.bit_replication
        )
        + struct.pack(
            ">d", profile.bit_confidence_min
        )
        + struct.pack(
            ">d", profile.pilot_score_min
        )
        + struct.pack(
            ">I", profile.max_geometry_hypotheses
        )
        + struct.pack(
            ">d", profile.geometry_ratio_tolerance
        )
        + struct.pack(
            ">I", len(profile.crop_retained_scales)
        )
        + b"".join(struct.pack(">d", scale) for scale in profile.crop_retained_scales)
        + struct.pack(">I", len(interpolation))
        + interpolation
    )


def v2_pilot_profile(profile: FingerprintV3Profile) -> FingerprintV2Profile:
    """Return the unique frozen V2 profile used only by V3 pilot/ORB fallback."""

    _validate_profile(profile)
    matches = tuple(
        candidate
        for candidate in load_v2_profiles()
        if (
            candidate.qim_delta,
            candidate.pilot_strength_rms,
            candidate.tile_size_px,
            candidate.payload_repetitions,
        )
        == (
            profile.qim_delta,
            profile.pilot_strength_rms,
            profile.tile_size_px,
            profile.payload_repetitions,
        )
    )
    if len(matches) != 1:
        raise ValueError("V3 profile must map to exactly one frozen V2 profile")
    return matches[0]


def _validate_fixed(value: Any) -> dict[str, Any]:
    fixed = _require_object(value, "fixed")
    _require_exact_keys(fixed, set(_EXPECTED_FIXED), "fixed")

    _require_real(fixed["qim_delta"], "fixed.qim_delta")
    _require_real(fixed["pilot_strength_rms"], "fixed.pilot_strength_rms")
    _require_real(fixed["spread_delta"], "fixed.spread_delta")
    _require_integer(fixed["spread_chips_per_bit"], "fixed.spread_chips_per_bit")
    _require_real(fixed["saturated_fraction_min"], "fixed.saturated_fraction_min")
    _require_integer(fixed["saturation_low"], "fixed.saturation_low")
    _require_integer(fixed["saturation_high"], "fixed.saturation_high")
    _require_integer(fixed["tiles_per_page"], "fixed.tiles_per_page")
    _require_integer(fixed["bit_replication"], "fixed.bit_replication")
    _require_real(fixed["bit_confidence_min"], "fixed.bit_confidence_min")
    _require_real(fixed["pilot_score_min"], "fixed.pilot_score_min")
    _require_integer(fixed["max_geometry_hypotheses"], "fixed.max_geometry_hypotheses")
    _require_real(fixed["geometry_ratio_tolerance"], "fixed.geometry_ratio_tolerance")
    _validate_crop_retained_scales(fixed["crop_retained_scales"])
    _require_string(fixed["resize_interpolation"], "fixed.resize_interpolation")

    for field, expected in _EXPECTED_FIXED.items():
        if fixed[field] != expected:
            raise ValueError(f"fixed.{field} is not supported by V3")
    return fixed


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
    if len(set(tile_sizes)) != len(tile_sizes) or len(set(repetitions)) != len(repetitions):
        raise ValueError("sweep values must not contain duplicates")
    return tile_sizes, repetitions


def _validate_profile(profile: FingerprintV3Profile) -> None:
    if type(profile) is not FingerprintV3Profile:
        raise TypeError("profile must be a FingerprintV3Profile")
    if profile.schema_version != 3:
        raise ValueError("profile schema_version must be 3")
    if not isinstance(profile.contract_sha256, bytes) or len(profile.contract_sha256) != 32:
        raise ValueError("profile contract_sha256 must contain exactly 32 bytes")

    positive_reals = (
        (profile.qim_delta, "profile.qim_delta"),
        (profile.pilot_strength_rms, "profile.pilot_strength_rms"),
        (profile.spread_delta, "profile.spread_delta"),
        (profile.geometry_ratio_tolerance, "profile.geometry_ratio_tolerance"),
    )
    for value, name in positive_reals:
        if _require_real(value, name) <= 0.0:
            raise ValueError(f"{name} must be positive")
    for value, name in (
        (profile.spread_chips_per_bit, "profile.spread_chips_per_bit"),
        (profile.tile_size_px, "profile.tile_size_px"),
        (profile.tiles_per_page, "profile.tiles_per_page"),
        (profile.payload_repetitions, "profile.payload_repetitions"),
        (profile.bit_replication, "profile.bit_replication"),
        (profile.max_geometry_hypotheses, "profile.max_geometry_hypotheses"),
    ):
        if _require_integer(value, name) <= 0:
            raise ValueError(f"{name} must be positive")
    for value, name in (
        (profile.saturated_fraction_min, "profile.saturated_fraction_min"),
        (profile.bit_confidence_min, "profile.bit_confidence_min"),
        (profile.pilot_score_min, "profile.pilot_score_min"),
    ):
        if not 0.0 <= _require_real(value, name) <= 1.0:
            raise ValueError(f"{name} must be between zero and one")
    if not 0 <= _require_integer(profile.saturation_low, "profile.saturation_low") < 256:
        raise ValueError("profile.saturation_low must be an 8-bit value")
    if not 0 <= _require_integer(profile.saturation_high, "profile.saturation_high") < 256:
        raise ValueError("profile.saturation_high must be an 8-bit value")
    if profile.saturation_low >= profile.saturation_high:
        raise ValueError("profile saturation bounds must be ordered")
    _validate_crop_retained_scales(profile.crop_retained_scales)
    if not isinstance(profile.resize_interpolation, str) or not profile.resize_interpolation:
        raise ValueError("profile.resize_interpolation must be a non-empty string")


def _validate_crop_retained_scales(value: Any) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError("crop_retained_scales must be a non-empty list of finite real numbers")
    scales = tuple(
        _require_real(item, "crop_retained_scales")
        for item in value
    )
    if any(scale <= 0.0 or scale > 1.0 for scale in scales):
        raise ValueError("crop_retained_scales must be in the interval (0, 1]")
    return scales


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


def _require_string(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    return value


def _require_integer_list(value: Any, name: str) -> tuple[int, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{name} must be a non-empty list of integers")
    return tuple(_require_integer(item, name) for item in value)
