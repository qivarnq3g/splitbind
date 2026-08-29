"""Deterministic semi-fragile region authentication reference."""

from __future__ import annotations

import hashlib
import hmac
import math
import struct
from dataclasses import dataclass
from typing import Mapping

import cv2
import numpy as np
from numpy.typing import NDArray

from splitbind_attack.ground_truth import NormalizedRect


Image = NDArray[np.uint8]


@dataclass(frozen=True, slots=True)
class EmbeddedIntegrityPage:
    image: Image
    embedded_regions: int
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class IntegrityDecision:
    score: float
    suspicious_regions: tuple[NormalizedRect, ...]
    evaluated_regions: int
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _Profile:
    region_size: int
    feature_positions: tuple[tuple[int, int], ...]
    feature_step: float
    partner_domain: bytes
    replica_shifts: tuple[int, ...]
    qim_delta: float
    coefficient_sets: tuple[tuple[tuple[int, int], ...], ...]
    minimum_replica_votes: int
    minimum_bit_confidence: float
    minimum_regions: int
    compression_ratio: float
    geometry_ratio: float
    high_confidence: float
    limitation_ids: Mapping[str, str]
    max_pixels: int
    key_min: int
    key_max: int
    nonce_min: int
    nonce_max: int


def embed_integrity(
    page: Image, key: bytes, nonce: bytes, profile: Mapping[str, object]
) -> EmbeddedIntegrityPage:
    """Embed 32-bit region tags into three key-derived partner regions."""

    parsed = _validate_profile(profile)
    source = _validate_inputs(page, key, nonce, parsed)
    regions = _regions(source.shape, parsed.region_size)
    if len(regions) < parsed.minimum_regions:
        return EmbeddedIntegrityPage(
            image=source.copy(),
            embedded_regions=0,
            limitations=(parsed.limitation_ids["insufficient_complete_regions"],),
        )

    luminance = _luminance(source)
    features = tuple(
        _content_feature(luminance[y : y + parsed.region_size, x : x + parsed.region_size], parsed)
        for x, y in regions
    )
    tags = tuple(_region_tag(feature, index, nonce, key) for index, feature in enumerate(features))
    partners = _partner_regions(len(regions), key, nonce, parsed)
    modified_luminance = luminance.copy()
    for source_index, tag in enumerate(tags):
        bits = _bytes_to_bits(tag)
        for replica, destinations in enumerate(partners):
            destination = destinations[source_index]
            x, y = regions[destination]
            block = modified_luminance[
                y : y + parsed.region_size, x : x + parsed.region_size
            ]
            modified_luminance[y : y + parsed.region_size, x : x + parsed.region_size] = (
                _embed_bits(block, bits, parsed.coefficient_sets[replica], parsed.qim_delta)
            )
    return EmbeddedIntegrityPage(
        image=_replace_luminance(source, modified_luminance),
        embedded_regions=len(regions),
        limitations=(),
    )


def verify_integrity(
    page: Image, key: bytes, nonce: bytes, profile: Mapping[str, object]
) -> IntegrityDecision:
    """Verify region tags and return conservative normalized localization evidence."""

    parsed = _validate_profile(profile)
    source = _validate_inputs(page, key, nonce, parsed)
    regions = _regions(source.shape, parsed.region_size)
    if len(regions) < parsed.minimum_regions:
        return IntegrityDecision(
            score=0.0,
            suspicious_regions=(),
            evaluated_regions=0,
            limitations=(parsed.limitation_ids["insufficient_complete_regions"],),
        )

    luminance = _luminance(source)
    features = tuple(
        _content_feature(luminance[y : y + parsed.region_size, x : x + parsed.region_size], parsed)
        for x, y in regions
    )
    expected = tuple(
        _region_tag(feature, index, nonce, key) for index, feature in enumerate(features)
    )
    partners = _partner_regions(len(regions), key, nonce, parsed)
    suspicious_indexes: list[int] = []
    evaluated = 0
    matches = 0
    confidences: list[float] = []
    mismatch_count = 0
    indeterminate_count = 0
    for source_index, expected_tag in enumerate(expected):
        replica_mismatches = 0
        usable_replicas = 0
        for replica, destinations in enumerate(partners):
            destination = destinations[source_index]
            x, y = regions[destination]
            block = luminance[y : y + parsed.region_size, x : x + parsed.region_size]
            actual, confidence = _extract_bits(
                block, parsed.coefficient_sets[replica], parsed.qim_delta
            )
            confidences.append(confidence)
            if confidence >= parsed.minimum_bit_confidence:
                usable_replicas += 1
                replica_mismatches += actual != expected_tag
        if usable_replicas < parsed.minimum_replica_votes:
            indeterminate_count += 1
            continue
        evaluated += 1
        if replica_mismatches >= parsed.minimum_replica_votes:
            suspicious_indexes.append(source_index)
            mismatch_count += 1
        else:
            matches += 1

    mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    mismatch_ratio = mismatch_count / evaluated if evaluated else 1.0
    limitations: tuple[str, ...] = ()
    if evaluated == 0 or indeterminate_count > len(regions) // 2:
        limitations = (parsed.limitation_ids["indeterminate"],)
    elif mismatch_ratio >= parsed.geometry_ratio and mean_confidence >= parsed.high_confidence:
        limitations = (parsed.limitation_ids["geometry_failure"],)
    elif mismatch_ratio >= parsed.compression_ratio and mean_confidence < parsed.high_confidence:
        limitations = (parsed.limitation_ids["strong_compression"],)

    if limitations:
        suspicious = ()
    else:
        height, width = source.shape[:2]
        suspicious = tuple(
            NormalizedRect(
                x=regions[index][0] / width,
                y=regions[index][1] / height,
                width=parsed.region_size / width,
                height=parsed.region_size / height,
            )
            for index in suspicious_indexes
        )
    return IntegrityDecision(
        score=matches / evaluated if evaluated else 0.0,
        suspicious_regions=suspicious,
        evaluated_regions=evaluated,
        limitations=limitations,
    )


def _region_tag(feature: bytes, region_index: int, nonce: bytes, key: bytes) -> bytes:
    message = feature + region_index.to_bytes(4, "big") + nonce
    return hmac.new(key, message, hashlib.sha256).digest()[:4]


def _content_feature(region: NDArray[np.uint8], profile: _Profile) -> bytes:
    coefficients = cv2.dct(region.astype(np.float32))
    quantized = []
    for row, column in profile.feature_positions:
        value = int(np.rint(float(coefficients[row, column]) / profile.feature_step))
        if not -32768 <= value <= 32767:
            raise ValueError("integrity profile feature encoding overflow")
        quantized.append(value)
    return b"".join(struct.pack(">h", value) for value in quantized)


def _embed_bits(
    region: NDArray[np.uint8],
    bits: tuple[int, ...],
    positions: tuple[tuple[int, int], ...],
    delta: float,
) -> NDArray[np.uint8]:
    coefficients = cv2.dct(region.astype(np.float32))
    for bit, (row, column) in zip(bits, positions, strict=True):
        scaled = float(coefficients[row, column]) / delta
        lattice = round(scaled)
        if lattice % 2 != bit:
            lower = lattice - 1
            upper = lattice + 1
            lattice = lower if abs(lower - scaled) <= abs(upper - scaled) else upper
        coefficients[row, column] = lattice * delta
    restored = cv2.idct(coefficients)
    return np.clip(np.rint(restored), 0, 255).astype(np.uint8)


def _extract_bits(
    region: NDArray[np.uint8],
    positions: tuple[tuple[int, int], ...],
    delta: float,
) -> tuple[bytes, float]:
    coefficients = cv2.dct(region.astype(np.float32))
    bits: list[int] = []
    margins: list[float] = []
    for row, column in positions:
        scaled = float(coefficients[row, column]) / delta
        lattice = round(scaled)
        bits.append(lattice & 1)
        margins.append(max(0.0, 1.0 - 2.0 * abs(scaled - lattice)))
    return _bits_to_bytes(bits), sum(margins) / len(margins)


def _partner_regions(
    count: int, key: bytes, nonce: bytes, profile: _Profile
) -> tuple[tuple[int, ...], ...]:
    order = tuple(
        sorted(
            range(count),
            key=lambda index: hmac.new(
                key,
                profile.partner_domain + b"\x00" + nonce + index.to_bytes(4, "big"),
                hashlib.sha256,
            ).digest(),
        )
    )
    rank = {source: position for position, source in enumerate(order)}
    mappings = []
    for shift in profile.replica_shifts:
        effective = shift % count
        if effective == 0:
            raise ValueError("integrity profile replica shift maps a region to itself")
        mappings.append(
            tuple(order[(rank[source] + effective) % count] for source in range(count))
        )
    return tuple(mappings)


def _regions(shape: tuple[int, ...], region_size: int) -> tuple[tuple[int, int], ...]:
    height, width = shape[:2]
    return tuple(
        (x, y)
        for y in range(0, height - region_size + 1, region_size)
        for x in range(0, width - region_size + 1, region_size)
    )


def _luminance(page: Image) -> NDArray[np.uint8]:
    if page.ndim == 2:
        return page.copy()
    return cv2.cvtColor(page, cv2.COLOR_BGR2GRAY)


def _replace_luminance(page: Image, luminance: NDArray[np.uint8]) -> Image:
    if page.ndim == 2:
        return luminance.copy()
    ycrcb = cv2.cvtColor(page, cv2.COLOR_BGR2YCrCb)
    ycrcb[..., 0] = luminance
    return cv2.cvtColor(ycrcb, cv2.COLOR_YCrCb2BGR)


def _bytes_to_bits(value: bytes) -> tuple[int, ...]:
    return tuple((byte >> shift) & 1 for byte in value for shift in range(7, -1, -1))


def _bits_to_bytes(bits: list[int]) -> bytes:
    return bytes(
        sum(bits[offset + index] << (7 - index) for index in range(8))
        for offset in range(0, len(bits), 8)
    )


def _validate_inputs(page: Image, key: bytes, nonce: bytes, profile: _Profile) -> Image:
    if not isinstance(page, np.ndarray):
        raise TypeError("page must be a numpy array")
    if page.dtype != np.uint8:
        raise TypeError("page must use uint8 samples")
    if page.ndim not in (2, 3):
        raise ValueError("page must be grayscale or channel-last BGR")
    if page.ndim == 3 and page.shape[2] != 3:
        raise ValueError("page channel count must be 1 or 3")
    if page.shape[0] == 0 or page.shape[1] == 0:
        raise ValueError("page dimensions must be non-empty")
    if int(page.shape[0]) * int(page.shape[1]) > profile.max_pixels:
        raise ValueError("page exceeds the 40 megapixels limit")
    _validate_secret("key", key, profile.key_min, profile.key_max)
    _validate_secret("nonce", nonce, profile.nonce_min, profile.nonce_max)
    return np.ascontiguousarray(page)


def _validate_secret(name: str, value: bytes, minimum: int, maximum: int) -> None:
    if not isinstance(value, bytes):
        raise TypeError(f"{name} must be bytes")
    if not minimum <= len(value) <= maximum:
        raise ValueError(f"{name} length must be in [{minimum}, {maximum}] bytes")


def _validate_profile(profile: Mapping[str, object]) -> _Profile:
    prefix = "integrity profile"
    if not isinstance(profile, Mapping):
        raise TypeError(f"{prefix} must be a mapping")
    expected_root = {
        "schema_version", "profile_id", "status", "region_size_px",
        "content_feature", "authentication", "partner_mapping", "embedding",
        "localization", "decision_policy", "input_bounds",
    }
    if set(profile) != expected_root:
        raise ValueError(f"{prefix} has missing or unsupported fields")
    if (
        profile.get("schema_version") != 1
        or profile.get("profile_id") != "splitbind-integrity-candidate-v1"
        or profile.get("status") != "research-candidate"
        or profile.get("region_size_px") != 128
    ):
        raise ValueError(f"{prefix} identity, status, and region size must match v1")
    content = _mapping(profile, "content_feature", prefix)
    authentication = _mapping(profile, "authentication", prefix)
    partner_mapping = _mapping(profile, "partner_mapping", prefix)
    embedding = _mapping(profile, "embedding", prefix)
    localization = _mapping(profile, "localization", prefix)
    decision_policy = _mapping(profile, "decision_policy", prefix)
    bounds = _mapping(profile, "input_bounds", prefix)
    _exact_keys(content, {"color_channel", "transform", "coefficient_band", "coefficient_positions", "quantization_step", "encoding"}, prefix)
    _exact_keys(authentication, {"algorithm", "tag_bytes", "binding_inputs", "placement", "exclude_destination_coefficients_from_feature"}, prefix)
    _exact_keys(partner_mapping, {"derivation", "domain", "replica_ring_shifts"}, prefix)
    _exact_keys(embedding, {"transform", "quantizer", "qim_delta", "tag_coefficient_sets", "minimum_replica_votes", "minimum_bit_confidence"}, prefix)
    _exact_keys(localization, {"coordinate_space", "score_range"}, prefix)
    _exact_keys(decision_policy, {"minimum_complete_regions", "strong_compression_mismatch_ratio", "geometry_failure_mismatch_ratio", "high_confidence_threshold", "limitation_ids"}, prefix)
    _exact_keys(bounds, {"supported_dtype", "supported_channels", "max_pixels", "key_bytes", "nonce_bytes", "partial_region_policy"}, prefix)
    required_literals = (
        (content.get("color_channel"), "luminance"), (content.get("transform"), "dct"),
        (content.get("coefficient_band"), "low-frequency-quantized"), (content.get("encoding"), "signed-int16-big-endian"),
        (authentication.get("algorithm"), "hmac-sha256"), (authentication.get("tag_bytes"), 4),
        (authentication.get("binding_inputs"), ["content_feature", "region_index_be32", "document_nonce"]),
        (authentication.get("placement"), "key-derived-partner-region"),
        (partner_mapping.get("derivation"), "hmac-sha256-sorted-ring-v1"),
        (authentication.get("exclude_destination_coefficients_from_feature"), True),
        (embedding.get("transform"), "dct"), (embedding.get("quantizer"), "parity-qim"),
        (localization.get("coordinate_space"), "normalized-xywh"),
        (localization.get("score_range"), [0.0, 1.0]), (bounds.get("supported_dtype"), "uint8"),
        (bounds.get("supported_channels"), [1, 3]), (bounds.get("partial_region_policy"), "ignore"),
    )
    if any(actual != wanted for actual, wanted in required_literals):
        raise ValueError(f"{prefix} contains unsupported algorithm choices")
    feature_positions = _positions(content.get("coefficient_positions"), 16, prefix)
    feature_step = _finite_positive(content.get("quantization_step"), prefix)
    shifts = _integer_tuple(partner_mapping.get("replica_ring_shifts"), prefix)
    boxes = embedding.get("tag_coefficient_sets")
    if not isinstance(boxes, list) or len(boxes) != len(shifts):
        raise ValueError(f"{prefix} tag coefficient sets must match replicas")
    coefficient_sets = tuple(_coefficient_box(box, prefix) for box in boxes)
    if any(len(values) != 32 for values in coefficient_sets):
        raise ValueError(f"{prefix} each tag coefficient set must contain 32 positions")
    if set(feature_positions) & set().union(*(set(values) for values in coefficient_sets)):
        raise ValueError(f"{prefix} feature and destination coefficients must be disjoint")
    limitation_ids = _mapping(decision_policy, "limitation_ids", prefix)
    _exact_keys(limitation_ids, {"strong_compression", "geometry_failure", "insufficient_complete_regions", "indeterminate"}, prefix)
    if any(not isinstance(value, str) or not value.startswith("integrity.") for value in limitation_ids.values()):
        raise ValueError(f"{prefix} limitation identifiers are invalid")
    key_bounds = _mapping(bounds, "key_bytes", prefix)
    nonce_bounds = _mapping(bounds, "nonce_bytes", prefix)
    _exact_keys(key_bounds, {"minimum", "maximum"}, prefix)
    _exact_keys(nonce_bounds, {"minimum", "maximum"}, prefix)
    parsed = _Profile(
        region_size=128,
        feature_positions=feature_positions,
        feature_step=feature_step,
        partner_domain=_nonempty_ascii(partner_mapping.get("domain"), prefix),
        replica_shifts=shifts,
        qim_delta=_finite_positive(embedding.get("qim_delta"), prefix),
        coefficient_sets=coefficient_sets,
        minimum_replica_votes=_positive_integer(embedding.get("minimum_replica_votes"), prefix),
        minimum_bit_confidence=_unit_float(embedding.get("minimum_bit_confidence"), prefix),
        minimum_regions=_positive_integer(decision_policy.get("minimum_complete_regions"), prefix),
        compression_ratio=_unit_float(decision_policy.get("strong_compression_mismatch_ratio"), prefix),
        geometry_ratio=_unit_float(decision_policy.get("geometry_failure_mismatch_ratio"), prefix),
        high_confidence=_unit_float(decision_policy.get("high_confidence_threshold"), prefix),
        limitation_ids={str(key): str(value) for key, value in limitation_ids.items()},
        max_pixels=_positive_integer(bounds.get("max_pixels"), prefix),
        key_min=_positive_integer(key_bounds.get("minimum"), prefix),
        key_max=_positive_integer(key_bounds.get("maximum"), prefix),
        nonce_min=_positive_integer(nonce_bounds.get("minimum"), prefix),
        nonce_max=_positive_integer(nonce_bounds.get("maximum"), prefix),
    )
    if parsed.max_pixels != 40_000_000 or parsed.minimum_regions <= len(parsed.replica_shifts):
        raise ValueError(f"{prefix} safety bounds are invalid")
    if parsed.minimum_replica_votes > len(parsed.replica_shifts):
        raise ValueError(f"{prefix} vote threshold exceeds replicas")
    if parsed.key_min > parsed.key_max or parsed.nonce_min > parsed.nonce_max:
        raise ValueError(f"{prefix} secret bounds are invalid")
    return parsed


def _mapping(parent: Mapping[str, object], key: str, prefix: str) -> Mapping[str, object]:
    value = parent.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{prefix} field {key} must be an object")
    return value


def _exact_keys(value: Mapping[str, object], expected: set[str], prefix: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{prefix} has missing or unsupported nested fields")


def _positions(value: object, count: int, prefix: str) -> tuple[tuple[int, int], ...]:
    if not isinstance(value, list) or len(value) != count:
        raise ValueError(f"{prefix} coefficient positions are invalid")
    positions = []
    for pair in value:
        if not isinstance(pair, list) or len(pair) != 2 or any(isinstance(item, bool) or not isinstance(item, int) or not 0 <= item < 128 for item in pair):
            raise ValueError(f"{prefix} coefficient positions are invalid")
        positions.append((pair[0], pair[1]))
    if len(set(positions)) != len(positions):
        raise ValueError(f"{prefix} coefficient positions must be unique")
    return tuple(positions)


def _coefficient_box(value: object, prefix: str) -> tuple[tuple[int, int], ...]:
    if not isinstance(value, Mapping) or set(value) != {"row_start", "column_start", "rows", "columns"}:
        raise ValueError(f"{prefix} tag coefficient box is invalid")
    values = tuple(value.get(key) for key in ("row_start", "column_start", "rows", "columns"))
    if any(isinstance(item, bool) or not isinstance(item, int) for item in values):
        raise ValueError(f"{prefix} tag coefficient box is invalid")
    row, column, rows, columns = values
    if row < 0 or column < 0 or rows < 1 or columns < 1 or row + rows > 128 or column + columns > 128:
        raise ValueError(f"{prefix} tag coefficient box is invalid")
    return tuple((r, c) for r in range(row, row + rows) for c in range(column, column + columns))


def _integer_tuple(value: object, prefix: str) -> tuple[int, ...]:
    if not isinstance(value, list) or not value or any(isinstance(item, bool) or not isinstance(item, int) or item < 1 for item in value):
        raise ValueError(f"{prefix} replica shifts are invalid")
    if len(set(value)) != len(value):
        raise ValueError(f"{prefix} replica shifts must be unique")
    return tuple(value)


def _finite_positive(value: object, prefix: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or float(value) <= 0.0:
        raise ValueError(f"{prefix} numeric value must be finite and positive")
    return float(value)


def _unit_float(value: object, prefix: str) -> float:
    result = _finite_positive(value, prefix)
    if result > 1.0:
        raise ValueError(f"{prefix} threshold must be in (0, 1]")
    return result


def _positive_integer(value: object, prefix: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{prefix} integer value must be positive")
    return value


def _nonempty_ascii(value: object, prefix: str) -> bytes:
    if not isinstance(value, str) or not value or len(value) > 128 or not value.isascii():
        raise ValueError(f"{prefix} domain must be bounded ASCII")
    return value.encode("ascii")
