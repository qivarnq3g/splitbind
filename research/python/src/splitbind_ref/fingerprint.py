"""Reference DWT-DCT-QIM fingerprint embedding and confidence voting.

The candidate pipeline is intentionally a research reference, not a promoted
profile.  It consumes the A1 candidate grid and A2 payload, ECC, and keyed tile
layout interfaces.  Runtime profiles additionally bind the document nonce and
page index needed to reproduce the keyed layout during verification.
"""

from __future__ import annotations

import hashlib
import hmac
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Literal, Mapping
from uuid import UUID

import numpy as np
from numpy.typing import NDArray

from .contracts import fingerprint_candidates, payload_profile
from .dwt_dct_qim import (
    dct2,
    embed_bits_in_band,
    haar_dwt2,
    haar_idwt2,
    qim_extract_pair,
)
from .ecc import EccDecodeError, decode_ecc, encode_ecc
from .payload import decode_payload, encode_payload
from .synchronization import SyncTemplate, align_page, build_sync_template
from .tile_layout import derive_tiles


PageImage = NDArray[np.uint8] | NDArray[np.uint16]
DecisionReason = Literal["decoded", "partial", "not_detected", "invalid_crc"]
_MASK_DOMAIN = b"splitbind-fingerprint-mask\x00"
_DECODE_THRESHOLD = 0.60


@dataclass(frozen=True, slots=True)
class FingerprintContext:
    issuance_id: UUID
    fingerprint_key: bytes
    document_nonce: bytes
    page_index: int


@dataclass(frozen=True, slots=True)
class EmbeddedPage:
    image: PageImage
    sync_template: SyncTemplate
    psnr_db: float
    embedded_repetitions: int


@dataclass(frozen=True, slots=True)
class DecodeVote:
    issuance_id: UUID | None
    confidence: float
    bit_error_rate: float | None
    reason: DecisionReason


@dataclass(frozen=True, slots=True)
class DecodeDecision:
    issuance_id: UUID | None
    confidence: float
    valid_votes: int
    bit_error_rate: float | None
    reason: DecisionReason


@dataclass(frozen=True, slots=True)
class _RuntimeProfile:
    schema_version: int
    qim_delta: float
    tile_size_px: int
    tiles_per_page: int
    payload_repetitions: int
    document_nonce: bytes
    page_index: int
    sync_template: SyncTemplate | None

    @property
    def tile_profile(self) -> dict[str, int]:
        return {
            "schema_version": self.schema_version,
            "tile_size_px": self.tile_size_px,
            "tiles_per_page": self.tiles_per_page,
        }


def embed_fingerprint(
    page_bgr: PageImage,
    context: FingerprintContext,
    profile: Mapping[str, object],
) -> EmbeddedPage:
    """Embed repeated, whitened A2 codewords into keyed page tiles."""

    page = _validate_page(page_bgr)
    validated_context = _validate_context(context)
    candidate = _validate_profile(profile)
    if candidate.document_nonce != validated_context.document_nonce:
        raise ValueError("profile document_nonce must match the embedding context")
    if candidate.page_index != validated_context.page_index:
        raise ValueError("profile page_index must match the embedding context")

    tiles = derive_tiles(
        page.shape[:2],
        validated_context.fingerprint_key,
        validated_context.document_nonce,
        validated_context.page_index,
        candidate.tile_profile,
    )
    codeword = encode_ecc(
        encode_payload(validated_context.issuance_id, candidate.schema_version),
        parity_symbols=payload_profile()["reed_solomon"]["parity_symbols"],
    )
    raw_bits = np.unpackbits(np.frombuffer(codeword, dtype=np.uint8), bitorder="big")
    bits = np.bitwise_xor(
        raw_bits,
        _mask_bits(
            validated_context.fingerprint_key,
            validated_context.document_nonce,
            validated_context.page_index,
            candidate.schema_version,
            raw_bits.size,
        ),
    )

    original_luminance = _luminance(page)
    modified_luminance = original_luminance.copy()
    for tile in tiles[: candidate.payload_repetitions]:
        tile_luminance = modified_luminance[
            tile.y : tile.y + tile.height, tile.x : tile.x + tile.width
        ]
        modified_luminance[
            tile.y : tile.y + tile.height, tile.x : tile.x + tile.width
        ] = _embed_tile(tile_luminance, bits, candidate.qim_delta)

    embedded_image = _replace_luminance(page, original_luminance, modified_luminance)
    error = embedded_image.astype(np.float64) - page.astype(np.float64)
    mse = float(np.mean(error * error))
    peak = float(np.iinfo(page.dtype).max)
    psnr_db = math.inf if mse == 0.0 else 10.0 * math.log10(peak * peak / mse)
    template = build_sync_template(_sync_view(embedded_image))
    return EmbeddedPage(
        image=embedded_image,
        sync_template=template,
        psnr_db=psnr_db,
        embedded_repetitions=candidate.payload_repetitions,
    )


def decode_fingerprint(
    page_bgr: PageImage,
    key: bytes,
    profiles: Iterable[Mapping[str, object]],
) -> DecodeDecision:
    """Try contracted candidates and return only CRC-valid attribution votes."""

    page = _validate_page(page_bgr)
    _validate_nonempty_bytes("key", key)
    candidates = tuple(_validate_profile(profile) for profile in profiles)
    if not candidates:
        raise ValueError("profiles must contain at least one candidate")

    votes: list[DecodeVote] = []
    for candidate in candidates:
        candidate_page = page
        if candidate.sync_template is not None:
            if page.dtype != np.uint8:
                raise ValueError("geometric alignment currently requires an uint8 page")
            alignment = align_page(page, candidate.sync_template)
            if alignment.image is None:
                continue
            candidate_page = alignment.image
        try:
            tiles = derive_tiles(
                candidate_page.shape[:2],
                key,
                candidate.document_nonce,
                candidate.page_index,
                candidate.tile_profile,
            )
        except (TypeError, ValueError):
            continue
        luminance = _luminance(candidate_page)
        for tile in tiles[: candidate.payload_repetitions]:
            tile_luminance = luminance[
                tile.y : tile.y + tile.height, tile.x : tile.x + tile.width
            ]
            bits, signal_confidence = _extract_tile(
                tile_luminance, _codeword_bit_count(), candidate.qim_delta
            )
            raw_bits = np.bitwise_xor(
                bits,
                _mask_bits(
                    key,
                    candidate.document_nonce,
                    candidate.page_index,
                    candidate.schema_version,
                    bits.size,
                ),
            )
            packed = np.packbits(raw_bits, bitorder="big").tobytes()
            votes.append(_decode_vote(packed, signal_confidence))
    return soft_vote(votes, _DECODE_THRESHOLD)


def soft_vote(votes: Iterable[DecodeVote], threshold: float) -> DecodeDecision:
    """Require weighted agreement among independently CRC-valid codewords."""

    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise TypeError("threshold must be a real number")
    if not math.isfinite(float(threshold)) or not 0.0 < float(threshold) <= 1.0:
        raise ValueError("threshold must be in (0, 1]")
    observed = tuple(votes)
    if any(not isinstance(vote, DecodeVote) for vote in observed):
        raise TypeError("votes must contain DecodeVote values")

    valid = [
        vote
        for vote in observed
        if vote.reason == "decoded" and vote.issuance_id is not None
    ]
    if not valid:
        reason: DecisionReason = (
            "invalid_crc" if any(vote.reason == "invalid_crc" for vote in observed) else "not_detected"
        )
        return DecodeDecision(None, 0.0, 0, None, reason)

    weights: dict[UUID, float] = defaultdict(float)
    grouped: dict[UUID, list[DecodeVote]] = defaultdict(list)
    for vote in valid:
        if not math.isfinite(vote.confidence) or not 0.0 <= vote.confidence <= 1.0:
            raise ValueError("vote confidence must be in [0, 1]")
        assert vote.issuance_id is not None
        weights[vote.issuance_id] += vote.confidence
        grouped[vote.issuance_id].append(vote)
    total_weight = sum(weights.values())
    if total_weight <= 0.0:
        return DecodeDecision(None, 0.0, 0, None, "not_detected")
    winner = min(weights, key=lambda issuance_id: (-weights[issuance_id], issuance_id.bytes))
    consensus = weights[winner] / total_weight
    winner_votes = grouped[winner]
    error_rates = [
        vote.bit_error_rate for vote in winner_votes if vote.bit_error_rate is not None
    ]
    bit_error_rate = (
        sum(error_rates) / len(error_rates) if error_rates else None
    )
    if consensus < float(threshold):
        return DecodeDecision(None, consensus, len(winner_votes), bit_error_rate, "partial")
    return DecodeDecision(
        winner,
        consensus,
        len(winner_votes),
        bit_error_rate,
        "decoded",
    )


def _embed_tile(luminance: NDArray[np.float64], bits: NDArray[np.uint8], delta: float):
    ll, lh, hl, hh, original_shape = haar_dwt2(luminance)
    hl = embed_bits_in_band(hl, bits, _coefficient_pairs(), delta)
    return haar_idwt2(ll, lh, hl, hh, original_shape)


def _extract_tile(luminance: NDArray[np.float64], bit_count: int, delta: float):
    _, _, hl, _, _ = haar_dwt2(luminance)
    pairs = _coefficient_pairs()
    capacity = (hl.shape[0] // 8) * (hl.shape[1] // 8) * len(pairs)
    if bit_count > capacity:
        raise ValueError(
            f"tile QIM capacity is {capacity} bits, but extraction needs {bit_count}"
        )
    bits = np.empty(bit_count, dtype=np.uint8)
    confidence_sum = 0.0
    bit_index = 0
    for y in range(0, hl.shape[0] - 7, 8):
        for x in range(0, hl.shape[1] - 7, 8):
            coefficients = dct2(hl[y : y + 8, x : x + 8])
            for first, second in pairs:
                if bit_index >= bit_count:
                    break
                extraction = qim_extract_pair(
                    coefficients[first], coefficients[second], delta
                )
                bits[bit_index] = extraction.bit
                confidence_sum += extraction.confidence
                bit_index += 1
            if bit_index >= bit_count:
                break
        if bit_index >= bit_count:
            break
    return bits, confidence_sum / bit_count


def _decode_vote(codeword: bytes, signal_confidence: float) -> DecodeVote:
    parity_symbols = payload_profile()["reed_solomon"]["parity_symbols"]
    try:
        payload = decode_ecc(codeword, parity_symbols=parity_symbols)
    except (EccDecodeError, ValueError):
        return DecodeVote(None, signal_confidence, None, "not_detected")
    try:
        decoded = decode_payload(payload)
    except ValueError as error:
        reason: DecisionReason = "invalid_crc" if "CRC" in str(error) else "not_detected"
        return DecodeVote(None, signal_confidence, None, reason)
    expected = np.unpackbits(
        np.frombuffer(encode_ecc(payload, parity_symbols), dtype=np.uint8), bitorder="big"
    )
    observed = np.unpackbits(np.frombuffer(codeword, dtype=np.uint8), bitorder="big")
    bit_error_rate = float(np.count_nonzero(expected != observed) / expected.size)
    return DecodeVote(decoded.issuance_id, signal_confidence, bit_error_rate, "decoded")


def _coefficient_pairs() -> tuple[tuple[tuple[int, int], tuple[int, int]], ...]:
    raw_pairs = fingerprint_candidates()["fixed"]["midband_pairs"]
    return tuple(
        (
            (int(raw_pair[0][0]), int(raw_pair[0][1])),
            (int(raw_pair[1][0]), int(raw_pair[1][1])),
        )
        for raw_pair in raw_pairs
    )


def _mask_bits(
    key: bytes,
    nonce: bytes,
    page_index: int,
    version: int,
    bit_count: int,
) -> NDArray[np.uint8]:
    byte_count = (bit_count + 7) // 8
    stream = bytearray()
    counter = 0
    binding = nonce + page_index.to_bytes(4, "big") + version.to_bytes(4, "big")
    while len(stream) < byte_count:
        stream.extend(
            hmac.new(
                key,
                _MASK_DOMAIN + binding + counter.to_bytes(4, "big"),
                hashlib.sha256,
            ).digest()
        )
        counter += 1
    return np.unpackbits(
        np.frombuffer(bytes(stream[:byte_count]), dtype=np.uint8), bitorder="big"
    )[:bit_count]


def _luminance(page: PageImage) -> NDArray[np.float64]:
    source = page.astype(np.float64)
    return 0.114 * source[..., 0] + 0.587 * source[..., 1] + 0.299 * source[..., 2]


def _replace_luminance(
    page: PageImage,
    original: NDArray[np.float64],
    modified: NDArray[np.float64],
) -> PageImage:
    peak = np.iinfo(page.dtype).max
    changed = modified != original
    if not np.any(changed):
        return page.copy()
    luminance_delta = (modified - original)[changed]
    integer_base = np.floor(luminance_delta)
    fractional = luminance_delta - integer_base

    # Choose floor/ceiling independently per B, G, and R channel.  The eight
    # weighted combinations quantize BT.601 luminance more finely than applying
    # one rounded integer to all channels, while channel offsets differ by at
    # most one code value and therefore preserve chroma to that tolerance.
    channel_patterns = np.asarray(
        [[(mask >> channel) & 1 for channel in range(3)] for mask in range(8)],
        dtype=np.float64,
    )
    luminance_levels = channel_patterns @ np.asarray(
        [0.114, 0.587, 0.299], dtype=np.float64
    )
    choices = np.argmin(np.abs(fractional[:, None] - luminance_levels), axis=1)
    offsets = integer_base[..., None] + channel_patterns[choices]
    result = page.copy()
    shifted = page[changed].astype(np.float64) + offsets
    result[changed] = np.clip(shifted, 0, peak).astype(page.dtype)
    return np.ascontiguousarray(result)


def _sync_view(page: PageImage) -> NDArray[np.uint8]:
    if page.dtype == np.uint8:
        return page
    peak = float(np.iinfo(page.dtype).max)
    return np.floor(page.astype(np.float64) * (255.0 / peak) + 0.5).astype(np.uint8)


def _codeword_bit_count() -> int:
    contract = payload_profile()["reed_solomon"]
    return int(contract["codeword_bytes"]) * 8


def _validate_page(page: PageImage) -> PageImage:
    if not isinstance(page, np.ndarray):
        raise TypeError("page must be a numpy array")
    if page.ndim != 3 or page.shape[2] != 3:
        raise ValueError("page must have BGR shape (height, width, 3)")
    if page.dtype not in (np.dtype(np.uint8), np.dtype(np.uint16)):
        raise TypeError("page must have an unsigned uint8 or uint16 dtype")
    if page.shape[0] == 0 or page.shape[1] == 0:
        raise ValueError("page must have non-empty dimensions")
    return np.ascontiguousarray(page)


def _validate_context(context: FingerprintContext) -> FingerprintContext:
    if not isinstance(context, FingerprintContext):
        raise TypeError("context must be a FingerprintContext")
    if not isinstance(context.issuance_id, UUID):
        raise TypeError("context issuance_id must be a UUID")
    _validate_nonempty_bytes("context fingerprint_key", context.fingerprint_key)
    _validate_nonempty_bytes("context document_nonce", context.document_nonce)
    _validate_page_index(context.page_index)
    return context


def _validate_profile(profile: Mapping[str, object]) -> _RuntimeProfile:
    required = {
        "schema_version",
        "qim_delta",
        "tile_size_px",
        "tiles_per_page",
        "payload_repetitions",
        "document_nonce",
        "page_index",
    }
    optional = {"sync_template"}
    if not isinstance(profile, Mapping):
        raise TypeError("profile must be a mapping")
    if not required <= set(profile) or set(profile) - required - optional:
        raise ValueError(
            f"profile must contain exactly {sorted(required)} plus optional sync_template"
        )
    contract = fingerprint_candidates()
    version = profile["schema_version"]
    if version != contract["schema_version"]:
        raise ValueError("unsupported profile schema_version")
    values = {
        "qim_delta": profile["qim_delta"],
        "tile_size_px": profile["tile_size_px"],
        "tiles_per_page": profile["tiles_per_page"],
        "payload_repetitions": profile["payload_repetitions"],
    }
    for name, value in values.items():
        if value not in contract["sweep"][name]:
            label = "repetitions" if name == "payload_repetitions" else name
            raise ValueError(f"{label} is not in the contracted candidate grid")
    repetitions = int(values["payload_repetitions"])
    if repetitions > int(values["tiles_per_page"]):
        raise ValueError("payload repetitions cannot exceed tiles_per_page")
    nonce = profile["document_nonce"]
    _validate_nonempty_bytes("profile document_nonce", nonce)
    page_index = profile["page_index"]
    _validate_page_index(page_index)
    sync_template = profile.get("sync_template")
    if sync_template is not None and not isinstance(sync_template, SyncTemplate):
        raise TypeError("sync_template must be a SyncTemplate")
    return _RuntimeProfile(
        schema_version=int(version),
        qim_delta=float(values["qim_delta"]),
        tile_size_px=int(values["tile_size_px"]),
        tiles_per_page=int(values["tiles_per_page"]),
        payload_repetitions=repetitions,
        document_nonce=nonce,
        page_index=page_index,
        sync_template=sync_template,
    )


def _validate_nonempty_bytes(name: str, value: object) -> None:
    if not isinstance(value, bytes) or not value:
        raise ValueError(f"{name} must be non-empty bytes")


def _validate_page_index(value: object) -> None:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not 0 <= value <= 0xFFFFFFFF
    ):
        raise ValueError("page_index must fit an unsigned 32-bit integer")
