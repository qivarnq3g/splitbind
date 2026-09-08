"""Bounded V3 embedding and candidate-local, fail-closed payload voting."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from itertools import islice
from typing import Iterable, Literal
from uuid import UUID

import numpy as np
from numpy.typing import NDArray

from splitbind_bench.metrics import compute_quality_metrics

from .ecc import EccDecodeError, decode_ecc_with_erasures, encode_ecc
# The frozen BT.601 raster math and input ceilings are version independent.
# Payload positions, codecs, profiles, and voting below belong exclusively to V3.
from .fingerprint_v2 import (
    _best_geometry_confidence,
    _luminance,
    _replace_luminance_once,
    _validate_canonical_shape,
    _validate_key,
    _validate_page,
    _validate_page_index,
)
from .fingerprint_v3_dct import CodewordEvidence, embed_codeword_v3, extract_codeword_v3
from .fingerprint_v3_profile import (
    FingerprintV3Profile, candidate_identifier_v3, load_v3_profiles, v2_pilot_profile,
)
from .fingerprint_v3_spread import (
    SpreadCodewordEvidence, embed_spread_codeword_v3, extract_spread_codeword_v3,
)
from .geometry_v3 import search_geometry_v3
from .payload import decode_payload, encode_payload
from .synchronization import SyncTemplate, build_sync_template
from .synchronization_v2 import embed_pilot_v2, synthesize_pilot_v2
from .tile_layout_v3 import derive_tiles_v3


@dataclass(frozen=True, slots=True)
class FingerprintV3Context:
    issuance_id: UUID
    fingerprint_key: bytes
    page_index: int


@dataclass(frozen=True, slots=True)
class EmbeddedPageV3:
    image: NDArray[np.uint8]
    psnr_db: float
    ssim: float
    embedded_repetitions: int
    sync_template: SyncTemplate | None


@dataclass(frozen=True, slots=True)
class DecodeV3Decision:
    issuance_id: UUID | None
    confidence: float
    valid_votes: int
    bit_error_rate: float | None
    status: Literal[
        "decoded", "partial_payload_evidence", "conflicting_payload_evidence",
        "payload_not_detected", "insufficient_sync_evidence", "geometry_rejected",
    ]


@dataclass(frozen=True, slots=True)
class _PayloadVoteV3:
    candidate_id: bytes
    geometry_matrix: tuple[float, ...]
    tile_ordinal: int
    codec: Literal["dct", "spread_darken", "spread_lighten"]
    issuance_id: UUID
    bit_error_rate: float | None


def embed_fingerprint_v3(
    page_bgr: NDArray[np.uint8],
    context: FingerprintV3Context,
    profile: FingerprintV3Profile,
) -> EmbeddedPageV3:
    """Embed pilot, select payload carriers, and measure the final uint8 raster."""

    if type(context) is not FingerprintV3Context:
        raise TypeError("context must be a FingerprintV3Context")
    if not isinstance(context.issuance_id, UUID):
        raise TypeError("context issuance_id must be a UUID")
    _validate_key(context.fingerprint_key)
    _validate_page_index(context.page_index)
    _validate_canonical_profile(profile)
    page = _validate_page(page_bgr)
    tiles = derive_tiles_v3(page.shape[:2], context.fingerprint_key, context.page_index, profile)
    original = _luminance(page)
    pilot_profile = v2_pilot_profile(profile)
    pilot = synthesize_pilot_v2(
        page.shape[:2], context.fingerprint_key, context.page_index, pilot_profile
    )
    modified = embed_pilot_v2(original, pilot, profile.pilot_strength_rms)
    codeword = encode_ecc(encode_payload(context.issuance_id))
    for tile in tiles[:profile.payload_repetitions]:
        region = np.s_[tile.y:tile.y + tile.height, tile.x:tile.x + tile.width]
        luminance = modified[region]
        bright_fraction = float(np.mean(luminance >= profile.saturation_high))
        dark_fraction = float(np.mean(luminance <= profile.saturation_low))
        if (bright_fraction >= profile.saturated_fraction_min
                or dark_fraction >= profile.saturated_fraction_min):
            # Spread samples need valid saturation headroom after pilot addition.
            # This is float clipping only; RGB is quantized exactly once below.
            modified[region] = embed_spread_codeword_v3(
                np.clip(luminance, 0.0, 255.0), codeword,
                context.fingerprint_key, context.page_index, profile,
            )
        else:
            modified[region] = embed_codeword_v3(
                luminance, codeword, context.fingerprint_key, context.page_index, profile
            )
    image = _replace_luminance_once(page, original, modified)
    quality = compute_quality_metrics(page, image)
    try:
        sync_template = build_sync_template(image)
    except ValueError as error:
        if str(error) != "page has insufficient features for an ORB sync template":
            raise
        sync_template = None
    return EmbeddedPageV3(
        image, quality.psnr_db, quality.ssim, profile.payload_repetitions, sync_template
    )


def decode_fingerprint_v3(
    page_bgr: NDArray[np.uint8],
    key: bytes,
    page_index: int,
    canonical_shape: tuple[int, int],
    profiles: Iterable[FingerprintV3Profile],
    orb_template: SyncTemplate | None = None,
) -> DecodeV3Decision:
    """Try bounded geometries and all V3 codecs; attribute only a unique quorum.

    Shape and pilot scores are geometry hints, not attribution. Only ECC/CRC-valid
    payloads vote. Geometry runtime failures propagate as execution errors.
    """

    _validate_key(key)
    _validate_page_index(page_index)
    canvas = _validate_canonical_shape(canonical_shape)
    candidates = _validate_profiles(profiles)
    page = _validate_page(page_bgr)
    votes: list[_PayloadVoteV3] = []
    scores: list[float] = []
    saw_geometry_rejection = False
    for profile in candidates:
        search = search_geometry_v3(page, key, page_index, canvas, profile, orb_template)
        saw_geometry_rejection |= search.sync_reason == "geometry_rejected"
        candidate_id = candidate_identifier_v3(profile)
        for hypothesis in search.hypotheses:
            scores.append(hypothesis.score)
            try:
                tiles = derive_tiles_v3(canvas, key, page_index, profile)
            except ValueError:
                # A canonical canvas can have insufficient tile capacity.
                continue
            luminance = _luminance(hypothesis.image)
            matrix = tuple(float(value) for value in hypothesis.source_to_canonical.flat)
            for ordinal, tile in enumerate(tiles[:profile.payload_repetitions]):
                region = luminance[tile.y:tile.y + tile.height, tile.x:tile.x + tile.width]
                evidence_by_codec = (
                    ("dct", extract_codeword_v3(region, key, page_index, profile)),
                    ("spread_darken", extract_spread_codeword_v3(region, key, page_index, profile, "darken")),
                    ("spread_lighten", extract_spread_codeword_v3(region, key, page_index, profile, "lighten")),
                )
                for codec, evidence in evidence_by_codec:
                    vote = _decode_payload_vote(evidence, candidate_id, matrix, ordinal, codec)
                    if vote is not None:
                        votes.append(vote)
    geometry_confidence = _best_geometry_confidence(scores)
    if not scores:
        status = "geometry_rejected" if saw_geometry_rejection else "insufficient_sync_evidence"
        return DecodeV3Decision(None, geometry_confidence, 0, None, status)
    return _decide_payload_votes(votes, candidates, geometry_confidence)


def _decode_payload_vote(
    evidence: CodewordEvidence | SpreadCodewordEvidence,
    candidate_id: bytes,
    geometry_matrix: tuple[float, ...],
    tile_ordinal: int,
    codec: Literal["dct", "spread_darken", "spread_lighten"],
) -> _PayloadVoteV3 | None:
    try:
        payload = decode_ecc_with_erasures(evidence.codeword, evidence.erase_positions)
        decoded = decode_payload(payload)
    except (EccDecodeError, ValueError):
        return None
    expected = encode_ecc(payload)
    observed_bits = np.unpackbits(np.frombuffer(evidence.codeword, np.uint8), bitorder="big")
    expected_bits = np.unpackbits(np.frombuffer(expected, np.uint8), bitorder="big")
    ber = float(np.count_nonzero(observed_bits != expected_bits) / expected_bits.size)
    return _PayloadVoteV3(candidate_id, geometry_matrix, tile_ordinal, codec, decoded.issuance_id, ber)


def _decide_payload_votes(
    votes: Iterable[_PayloadVoteV3],
    profiles: tuple[FingerprintV3Profile, ...],
    geometry_confidence: float,
) -> DecodeV3Decision:
    # Preserve UUID distinctions BEFORE collapsing geometry/codec provenance.
    # A minority conflicting UUID must fail closed even on the same tile.
    by_identity: dict[tuple[bytes, UUID], dict[int, _PayloadVoteV3]] = defaultdict(dict)
    observed_ids: set[UUID] = set()
    for vote in votes:
        observed_ids.add(vote.issuance_id)
        by_identity[vote.candidate_id, vote.issuance_id].setdefault(vote.tile_ordinal, vote)
    if not by_identity:
        return DecodeV3Decision(None, geometry_confidence, 0, None, "payload_not_detected")
    repetitions = {candidate_identifier_v3(profile): profile.payload_repetitions for profile in profiles}
    strongest_key, supporting = max(
        by_identity.items(),
        key=lambda item: (len(item[1]) / repetitions[item[0][0]], len(item[1])),
    )
    support = len(supporting) / repetitions[strongest_key[0]]
    errors = [vote.bit_error_rate for vote in supporting.values() if vote.bit_error_rate is not None]
    ber = sum(errors) / len(errors) if errors else None
    if len(observed_ids) > 1:
        status = "conflicting_payload_evidence"
    elif len(supporting) >= 2 and support >= 0.60:
        status = "decoded"
    else:
        status = "partial_payload_evidence"
    return DecodeV3Decision(
        strongest_key[1] if status == "decoded" else None, support, len(supporting), ber, status
    )


def _validate_canonical_profile(profile: FingerprintV3Profile) -> None:
    candidate_identifier_v3(profile)
    if profile not in load_v3_profiles():
        raise ValueError("profile must be an exact profile from the frozen V3 grid")


def _validate_profiles(profiles: Iterable[FingerprintV3Profile]) -> tuple[FingerprintV3Profile, ...]:
    supplied = tuple(islice(profiles, 17))
    if not supplied:
        raise ValueError("profiles must contain at least one V3 candidate")
    if len(supplied) > 16:
        raise ValueError("profiles must contain at most 16 V3 candidates")
    for profile in supplied:
        _validate_canonical_profile(profile)
    identifiers = [candidate_identifier_v3(profile) for profile in supplied]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("profiles contain a duplicate candidate identifier")
    return supplied
