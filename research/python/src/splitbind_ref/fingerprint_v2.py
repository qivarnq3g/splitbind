"""Public, bounded V2 fingerprint embedding and evidence-only decoding."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from itertools import islice
from typing import Iterable, Literal
from uuid import UUID

import numpy as np
from numpy.typing import NDArray

from splitbind_bench.metrics import compute_quality_metrics

from .ecc import EccDecodeError, decode_ecc_with_erasures, encode_ecc
from .fingerprint_v2_codec import CodewordEvidence, embed_codeword_v2, extract_codeword_v2
from .fingerprint_v2_profile import (
    FingerprintV2Profile,
    candidate_identifier_v2,
    load_v2_profiles,
)
from .payload import decode_payload, encode_payload
from .synchronization_v2 import align_page_v2, embed_pilot_v2, synthesize_pilot_v2
from .tile_layout_v2 import derive_tiles_v2


_MAX_PROFILES = 16
_CANDIDATE_SUPPORT_THRESHOLD = 0.60
_BT601_BGR = np.asarray((0.114, 0.587, 0.299), dtype=np.float64)
_MAX_PAGE_PIXELS = 40_000_000


@dataclass(frozen=True, slots=True)
class FingerprintV2Context:
    issuance_id: UUID
    fingerprint_key: bytes
    page_index: int


@dataclass(frozen=True, slots=True)
class EmbeddedPageV2:
    image: NDArray[np.uint8]
    psnr_db: float
    ssim: float
    embedded_repetitions: int


@dataclass(frozen=True, slots=True)
class DecodeV2Decision:
    issuance_id: UUID | None
    confidence: float
    valid_votes: int
    bit_error_rate: float | None
    status: Literal[
        "decoded",
        "partial_payload_evidence",
        "payload_not_detected",
        "insufficient_sync_evidence",
        "geometry_rejected",
    ]


@dataclass(frozen=True, slots=True)
class _PayloadVoteV2:
    candidate_id: bytes
    tile_ordinal: int
    issuance_id: UUID
    bit_error_rate: float | None


def embed_fingerprint_v2(
    page_bgr: NDArray[np.uint8],
    context: FingerprintV2Context,
    profile: FingerprintV2Profile,
) -> EmbeddedPageV2:
    """Embed the V2 pilot then replicated payload with one final BT.601 raster pass."""

    validated_context = _validate_context(context)
    _validate_canonical_profile(profile)
    page = _validate_page(page_bgr)
    tiles = derive_tiles_v2(
        page.shape[:2],
        validated_context.fingerprint_key,
        validated_context.page_index,
        profile,
    )
    if profile.payload_repetitions > len(tiles):
        raise ValueError("payload_repetitions cannot exceed the derived V2 tile count")

    original_luminance = _luminance(page)
    pilot = synthesize_pilot_v2(
        page.shape[:2], validated_context.fingerprint_key, validated_context.page_index, profile
    )
    modified_luminance = embed_pilot_v2(
        original_luminance, pilot, profile.pilot_strength_rms
    )
    codeword = encode_ecc(encode_payload(validated_context.issuance_id))
    for tile in tiles[: profile.payload_repetitions]:
        tile_luminance = modified_luminance[
            tile.y : tile.y + tile.height, tile.x : tile.x + tile.width
        ]
        modified_luminance[
            tile.y : tile.y + tile.height, tile.x : tile.x + tile.width
        ] = embed_codeword_v2(
            tile_luminance,
            codeword,
            validated_context.fingerprint_key,
            validated_context.page_index,
            profile,
        )

    image = _replace_luminance_once(page, original_luminance, modified_luminance)
    quality = compute_quality_metrics(page, image)
    return EmbeddedPageV2(
        image=image,
        psnr_db=quality.psnr_db,
        ssim=quality.ssim,
        embedded_repetitions=profile.payload_repetitions,
    )


def decode_fingerprint_v2(
    page_bgr: NDArray[np.uint8],
    key: bytes,
    page_index: int,
    canonical_shape: tuple[int, int],
    profiles: Iterable[FingerprintV2Profile],
) -> DecodeV2Decision:
    """Return attribution only after candidate-local CRC-valid tile quorum.

    Alignment runtime failures deliberately propagate.  They are execution
    errors, not evidence states, and Task 6 maps them to benchmark
    ``execution_error`` rows.
    """

    _validate_key(key)
    _validate_page_index(page_index)
    canonical_canvas = _validate_canonical_shape(canonical_shape)
    candidates = _validate_profiles(profiles)
    page = _validate_page(page_bgr)

    votes: list[_PayloadVoteV2] = []
    geometry_scores: list[float] = []
    saw_aligned = False
    saw_geometry_rejection = False

    for profile in candidates:
        alignment = align_page_v2(page, key, page_index, profile, canonical_canvas)
        geometry_scores.append(alignment.pilot_score)
        if alignment.reason == "geometry_rejected":
            saw_geometry_rejection = True
            continue
        if alignment.reason != "aligned" or alignment.image is None:
            continue

        saw_aligned = True
        try:
            tiles = derive_tiles_v2(alignment.image.shape[:2], key, page_index, profile)
        except ValueError:
            # An accepted geometry can still be too small for this candidate's
            # contracted tile count (for example, a crop).  It is no payload
            # evidence, not a fabricated safety rejection.
            continue
        luminance = _luminance(alignment.image)
        for tile_ordinal, tile in enumerate(tiles[: profile.payload_repetitions]):
            evidence = extract_codeword_v2(
                luminance[tile.y : tile.y + tile.height, tile.x : tile.x + tile.width],
                key,
                page_index,
                profile,
            )
            vote = _decode_payload_vote(
                evidence,
                candidate_identifier_v2(profile),
                tile_ordinal,
            )
            if vote is not None:
                votes.append(vote)

    geometry_confidence = _best_geometry_confidence(geometry_scores)
    if not saw_aligned:
        if saw_geometry_rejection:
            return DecodeV2Decision(
                None, geometry_confidence, 0, None, "geometry_rejected"
            )
        return DecodeV2Decision(
            None, geometry_confidence, 0, None, "insufficient_sync_evidence"
        )
    return _decide_payload_votes(votes, candidates, geometry_confidence)


def _decide_payload_votes(
    votes: Iterable[_PayloadVoteV2],
    profiles: tuple[FingerprintV2Profile, ...],
    geometry_confidence: float,
) -> DecodeV2Decision:
    unique: dict[tuple[bytes, int], _PayloadVoteV2] = {}
    for vote in votes:
        provenance = (vote.candidate_id, vote.tile_ordinal)
        existing = unique.setdefault(provenance, vote)
        if existing != vote:
            raise ValueError("duplicate V2 tile provenance has conflicting evidence")
    if not unique:
        return DecodeV2Decision(
            None, geometry_confidence, 0, None, "payload_not_detected"
        )

    repetitions_by_candidate = {
        candidate_identifier_v2(profile): profile.payload_repetitions for profile in profiles
    }
    by_candidate: dict[bytes, dict[UUID, list[_PayloadVoteV2]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for vote in unique.values():
        by_candidate[vote.candidate_id][vote.issuance_id].append(vote)

    support_groups: list[tuple[bytes, UUID, float, list[_PayloadVoteV2]]] = []
    eligible: list[tuple[bytes, UUID, float, list[_PayloadVoteV2]]] = []
    for candidate_id, by_issuance in by_candidate.items():
        repetitions = repetitions_by_candidate[candidate_id]
        for issuance_id, supporting in by_issuance.items():
            support = len(supporting) / repetitions
            group = (candidate_id, issuance_id, support, supporting)
            support_groups.append(group)
            if len(supporting) >= 2 and support >= _CANDIDATE_SUPPORT_THRESHOLD:
                eligible.append(group)

    observed_issuances = {vote.issuance_id for vote in unique.values()}
    if len(observed_issuances) != 1:
        strongest = max(support_groups, key=lambda group: (group[2], len(group[3])))
        return DecodeV2Decision(
            None,
            strongest[2],
            len(strongest[3]),
            _mean_bit_error_rate(strongest[3]),
            "partial_payload_evidence",
        )

    if not eligible:
        strongest = max(support_groups, key=lambda group: (group[2], len(group[3])))
        return DecodeV2Decision(
            None,
            strongest[2],
            len(strongest[3]),
            _mean_bit_error_rate(strongest[3]),
            "partial_payload_evidence",
        )

    issuance_id = next(iter(observed_issuances))
    winning = [group for group in eligible if group[1] == issuance_id]
    winner = max(winning, key=lambda group: (group[2], len(group[3])))
    return DecodeV2Decision(
        issuance_id,
        winner[2],
        len(winner[3]),
        _mean_bit_error_rate(winner[3]),
        "decoded",
    )


def _decode_payload_vote(
    evidence: CodewordEvidence, candidate_id: bytes, tile_ordinal: int
) -> _PayloadVoteV2 | None:
    try:
        payload = decode_ecc_with_erasures(evidence.codeword, evidence.erase_positions)
        decoded = decode_payload(payload)
    except (EccDecodeError, ValueError):
        return None
    expected = encode_ecc(payload)
    observed_bits = np.unpackbits(np.frombuffer(evidence.codeword, dtype=np.uint8), bitorder="big")
    expected_bits = np.unpackbits(np.frombuffer(expected, dtype=np.uint8), bitorder="big")
    return _PayloadVoteV2(
        candidate_id=candidate_id,
        tile_ordinal=tile_ordinal,
        issuance_id=decoded.issuance_id,
        bit_error_rate=float(np.count_nonzero(observed_bits != expected_bits) / expected_bits.size),
    )


def _luminance(page: NDArray[np.uint8]) -> NDArray[np.float64]:
    return page.astype(np.float64) @ _BT601_BGR


def _replace_luminance_once(
    page: NDArray[np.uint8],
    original: NDArray[np.float64],
    modified: NDArray[np.float64],
) -> NDArray[np.uint8]:
    changed = modified != original
    if not np.any(changed):
        return page.copy()
    luminance_delta = (modified - original)[changed]
    integer_base = np.floor(luminance_delta)
    fractional = luminance_delta - integer_base
    channel_patterns = np.asarray(
        [[(mask >> channel) & 1 for channel in range(3)] for mask in range(8)],
        dtype=np.float64,
    )
    luminance_levels = channel_patterns @ _BT601_BGR
    choices = np.argmin(np.abs(fractional[:, None] - luminance_levels), axis=1)
    offsets = integer_base[:, None] + channel_patterns[choices]
    result = page.copy()
    shifted = page[changed].astype(np.float64) + offsets
    result[changed] = np.clip(shifted, 0, 255).astype(np.uint8)
    return np.ascontiguousarray(result)


def _validate_page(page: object) -> NDArray[np.uint8]:
    if not isinstance(page, np.ndarray):
        raise TypeError("page must be a numpy array")
    if page.ndim != 3 or page.shape[2] != 3:
        raise ValueError("page must have BGR shape (height, width, 3)")
    if page.dtype != np.uint8:
        raise TypeError("V2 page must have uint8 dtype")
    if page.shape[0] == 0 or page.shape[1] == 0:
        raise ValueError("page must have non-empty dimensions")
    if page.shape[0] * page.shape[1] > _MAX_PAGE_PIXELS:
        raise ValueError("page exceeds the 40-megapixel processing ceiling")
    return np.ascontiguousarray(page)


def _validate_context(context: object) -> FingerprintV2Context:
    if type(context) is not FingerprintV2Context:
        raise TypeError("context must be a FingerprintV2Context")
    if not isinstance(context.issuance_id, UUID):
        raise TypeError("context issuance_id must be a UUID")
    _validate_key(context.fingerprint_key)
    _validate_page_index(context.page_index)
    return context


def _validate_profiles(profiles: Iterable[FingerprintV2Profile]) -> tuple[FingerprintV2Profile, ...]:
    supplied = tuple(islice(profiles, _MAX_PROFILES + 1))
    if not supplied:
        raise ValueError("profiles must contain at least one V2 candidate")
    if len(supplied) > _MAX_PROFILES:
        raise ValueError("profiles must contain at most 16 V2 candidates")
    for profile in supplied:
        _validate_canonical_profile(profile)
    identifiers = [candidate_identifier_v2(profile) for profile in supplied]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("profiles contain a duplicate candidate identifier")
    return supplied


def _validate_profile(profile: object) -> None:
    if type(profile) is not FingerprintV2Profile:
        raise TypeError("profile must be a FingerprintV2Profile")
    if profile.schema_version != 2:
        raise ValueError("profile schema_version must be 2")
    if (
        not math.isfinite(profile.qim_delta)
        or profile.qim_delta <= 0.0
        or not math.isfinite(profile.pilot_strength_rms)
        or profile.pilot_strength_rms <= 0.0
    ):
        raise ValueError("profile strengths must be finite and positive")
    if profile.payload_repetitions <= 0 or profile.payload_repetitions > profile.tiles_per_page:
        raise ValueError("profile payload_repetitions must fit tiles_per_page")
    candidate_identifier_v2(profile)


def _validate_canonical_profile(profile: object) -> None:
    _validate_profile(profile)
    if profile not in load_v2_profiles():
        raise ValueError("profile must be an exact profile from the frozen V2 grid")


def _validate_canonical_shape(canonical_shape: object) -> tuple[int, int]:
    if not isinstance(canonical_shape, (tuple, list)) or len(canonical_shape) != 2:
        raise ValueError("canonical_shape must contain positive (height, width) integers")
    height, width = canonical_shape
    if (
        isinstance(height, bool)
        or isinstance(width, bool)
        or not isinstance(height, (int, np.integer))
        or not isinstance(width, (int, np.integer))
        or height <= 0
        or width <= 0
    ):
        raise ValueError("canonical_shape must contain positive (height, width) integers")
    if height * width > _MAX_PAGE_PIXELS:
        raise ValueError("canonical_shape exceeds the 40-megapixel processing ceiling")
    return int(height), int(width)


def _validate_key(key: object) -> None:
    if not isinstance(key, bytes) or not key:
        raise ValueError("key must be non-empty bytes")


def _validate_page_index(page_index: object) -> None:
    if (
        not isinstance(page_index, int)
        or isinstance(page_index, bool)
        or not 0 <= page_index <= 0xFFFFFFFF
    ):
        raise ValueError("page_index must fit an unsigned 32-bit integer")


def _best_geometry_confidence(scores: Iterable[float]) -> float:
    finite = [float(score) for score in scores if math.isfinite(float(score))]
    return max((float(np.clip(score, -1.0, 1.0)) for score in finite), default=0.0)


def _mean_bit_error_rate(votes: Iterable[_PayloadVoteV2]) -> float | None:
    values = [vote.bit_error_rate for vote in votes if vote.bit_error_rate is not None]
    return sum(values) / len(values) if values else None
