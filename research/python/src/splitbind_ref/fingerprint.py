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
import struct
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
from .synchronization import (
    SyncTemplate,
    align_page,
    build_sync_template,
    validate_sync_template,
)
from .tile_layout import derive_tiles


PageImage = NDArray[np.uint8] | NDArray[np.uint16]
DecisionReason = Literal["decoded", "partial", "not_detected", "invalid_crc"]
_MASK_DOMAIN = b"splitbind-fingerprint-mask\x00"
_CANDIDATE_ID_MARKER = b"SBFP\x01"
_MAX_CANDIDATES = 48
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
    candidate_id: bytes
    tile_ordinal: int
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
class _AlgorithmSettings:
    block_size: int
    coefficient_pairs: tuple[tuple[tuple[int, int], tuple[int, int]], ...]
    luminance_coefficients: tuple[float, float, float]


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
    algorithm: _AlgorithmSettings
    candidate_id: bytes

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
            candidate.candidate_id,
            raw_bits.size,
        ),
    )

    original_luminance = _luminance(page, candidate.algorithm)
    modified_luminance = original_luminance.copy()
    for tile in tiles[: candidate.payload_repetitions]:
        tile_luminance = modified_luminance[
            tile.y : tile.y + tile.height, tile.x : tile.x + tile.width
        ]
        modified_luminance[
            tile.y : tile.y + tile.height, tile.x : tile.x + tile.width
        ] = _embed_tile(
            tile_luminance, bits, candidate.qim_delta, candidate.algorithm
        )

    embedded_image = _replace_luminance(
        page, original_luminance, modified_luminance, candidate.algorithm
    )
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
    supplied_profiles = tuple(profiles)
    if not supplied_profiles:
        raise ValueError("profiles must contain at least one candidate")
    if len(supplied_profiles) > _MAX_CANDIDATES:
        raise ValueError(f"profiles must contain at most {_MAX_CANDIDATES} candidates")
    candidates = tuple(_validate_profile(profile) for profile in supplied_profiles)
    identifiers = [candidate.candidate_id for candidate in candidates]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("profiles contain a duplicate candidate identifier")

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
        luminance = _luminance(candidate_page, candidate.algorithm)
        for tile_ordinal, tile in enumerate(tiles[: candidate.payload_repetitions]):
            tile_luminance = luminance[
                tile.y : tile.y + tile.height, tile.x : tile.x + tile.width
            ]
            bits, signal_confidence = _extract_tile(
                tile_luminance,
                _codeword_bit_count(),
                candidate.qim_delta,
                candidate.algorithm,
            )
            raw_bits = np.bitwise_xor(
                bits,
                _mask_bits(
                    key,
                    candidate.document_nonce,
                    candidate.page_index,
                    candidate.candidate_id,
                    bits.size,
                ),
            )
            packed = np.packbits(raw_bits, bitorder="big").tobytes()
            votes.append(
                _decode_vote(
                    packed,
                    signal_confidence,
                    candidate.candidate_id,
                    tile_ordinal,
                )
            )
    return soft_vote(votes, _DECODE_THRESHOLD)


def candidate_identifier(profile: Mapping[str, object]) -> bytes:
    """Return the frozen Rust-reproducible candidate identifier.

    The layout is ``b"SBFP\\x01"`` followed by schema version as u32 BE,
    QIM delta as IEEE-754 f64 BE, and tile size, tiles per page, and payload
    repetitions as u32 BE values, in that order.
    """

    return _validate_profile(profile).candidate_id


def soft_vote(votes: Iterable[DecodeVote], threshold: float) -> DecodeDecision:
    """Require candidate-local agreement among distinct CRC-valid repetitions."""

    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise TypeError("threshold must be a real number")
    if not math.isfinite(float(threshold)) or not 0.0 < float(threshold) <= 1.0:
        raise ValueError("threshold must be in (0, 1]")
    observed = tuple(votes)
    if any(not isinstance(vote, DecodeVote) for vote in observed):
        raise TypeError("votes must contain DecodeVote values")
    unique: dict[tuple[bytes, int], DecodeVote] = {}
    for vote in observed:
        _validate_vote(vote)
        provenance = (vote.candidate_id, vote.tile_ordinal)
        previous = unique.setdefault(provenance, vote)
        if previous != vote:
            raise ValueError("duplicate provenance has conflicting evidence")

    evidence = tuple(unique.values())
    valid = [
        vote
        for vote in evidence
        if vote.reason == "decoded" and vote.issuance_id is not None
    ]
    if not valid:
        reason: DecisionReason = (
            "invalid_crc" if any(vote.reason == "invalid_crc" for vote in evidence) else "not_detected"
        )
        return DecodeDecision(None, 0.0, 0, None, reason)

    by_candidate: dict[bytes, list[DecodeVote]] = defaultdict(list)
    for vote in evidence:
        by_candidate[vote.candidate_id].append(vote)
    support_groups: list[tuple[bytes, UUID, float, list[DecodeVote]]] = []
    eligible: list[tuple[bytes, UUID, float, list[DecodeVote]]] = []
    for candidate_id, candidate_evidence in by_candidate.items():
        by_issuance: dict[UUID, list[DecodeVote]] = defaultdict(list)
        for vote in candidate_evidence:
            if vote.reason == "decoded" and vote.issuance_id is not None:
                by_issuance[vote.issuance_id].append(vote)
        for issuance_id, supporting in by_issuance.items():
            support_ratio = len(supporting) / len(candidate_evidence)
            group = (candidate_id, issuance_id, support_ratio, supporting)
            support_groups.append(group)
            if len(supporting) >= 2 and support_ratio >= float(threshold):
                eligible.append(group)

    if not eligible:
        strongest = max(support_groups, key=lambda item: (item[2], len(item[3])))
        error_rates = [
            vote.bit_error_rate
            for vote in strongest[3]
            if vote.bit_error_rate is not None
        ]
        bit_error_rate = sum(error_rates) / len(error_rates) if error_rates else None
        return DecodeDecision(
            None,
            strongest[2],
            len(strongest[3]),
            bit_error_rate,
            "partial",
        )

    eligible_issuance_ids = {group[1] for group in eligible}
    if len(eligible_issuance_ids) != 1:
        return DecodeDecision(
            None,
            max(group[2] for group in eligible),
            max(len(group[3]) for group in eligible),
            None,
            "partial",
        )
    winner = next(iter(eligible_issuance_ids))
    winner_groups = [group for group in eligible if group[1] == winner]
    winner_votes = [vote for group in winner_groups for vote in group[3]]
    consensus = max(group[2] for group in winner_groups)
    error_rates = [vote.bit_error_rate for vote in winner_votes if vote.bit_error_rate is not None]
    bit_error_rate = sum(error_rates) / len(error_rates) if error_rates else None
    return DecodeDecision(
        winner,
        consensus,
        len(winner_votes),
        bit_error_rate,
        "decoded",
    )


def _validate_vote(vote: DecodeVote) -> None:
    if (
        not isinstance(vote.candidate_id, bytes)
        or len(vote.candidate_id) != 29
        or not vote.candidate_id.startswith(_CANDIDATE_ID_MARKER)
    ):
        raise ValueError("vote candidate_id must be a canonical candidate identifier")
    if (
        not isinstance(vote.tile_ordinal, int)
        or isinstance(vote.tile_ordinal, bool)
        or vote.tile_ordinal < 0
    ):
        raise ValueError("vote tile_ordinal must be a non-negative integer")
    if not math.isfinite(vote.confidence) or not 0.0 <= vote.confidence <= 1.0:
        raise ValueError("vote confidence must be in [0, 1]")


def _embed_tile(
    luminance: NDArray[np.float64],
    bits: NDArray[np.uint8],
    delta: float,
    algorithm: _AlgorithmSettings,
):
    ll, lh, hl, hh, original_shape = haar_dwt2(luminance)
    hl = embed_bits_in_band(hl, bits, algorithm.coefficient_pairs, delta)
    return haar_idwt2(ll, lh, hl, hh, original_shape)


def _extract_tile(
    luminance: NDArray[np.float64],
    bit_count: int,
    delta: float,
    algorithm: _AlgorithmSettings,
):
    _, _, hl, _, _ = haar_dwt2(luminance)
    pairs = algorithm.coefficient_pairs
    block_size = algorithm.block_size
    capacity = (
        (hl.shape[0] // block_size)
        * (hl.shape[1] // block_size)
        * len(pairs)
    )
    if bit_count > capacity:
        raise ValueError(
            f"tile QIM capacity is {capacity} bits, but extraction needs {bit_count}"
        )
    bits = np.empty(bit_count, dtype=np.uint8)
    confidence_sum = 0.0
    bit_index = 0
    for y in range(0, hl.shape[0] - block_size + 1, block_size):
        for x in range(0, hl.shape[1] - block_size + 1, block_size):
            coefficients = dct2(
                hl[y : y + block_size, x : x + block_size]
            )
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


def _decode_vote(
    codeword: bytes,
    signal_confidence: float,
    candidate_id: bytes,
    tile_ordinal: int,
) -> DecodeVote:
    parity_symbols = payload_profile()["reed_solomon"]["parity_symbols"]
    try:
        payload = decode_ecc(codeword, parity_symbols=parity_symbols)
    except (EccDecodeError, ValueError):
        return DecodeVote(
            candidate_id, tile_ordinal, None, signal_confidence, None, "not_detected"
        )
    try:
        decoded = decode_payload(payload)
    except ValueError as error:
        reason: DecisionReason = "invalid_crc" if "CRC" in str(error) else "not_detected"
        return DecodeVote(candidate_id, tile_ordinal, None, signal_confidence, None, reason)
    expected = np.unpackbits(
        np.frombuffer(encode_ecc(payload, parity_symbols), dtype=np.uint8), bitorder="big"
    )
    observed = np.unpackbits(np.frombuffer(codeword, dtype=np.uint8), bitorder="big")
    bit_error_rate = float(np.count_nonzero(expected != observed) / expected.size)
    return DecodeVote(
        candidate_id,
        tile_ordinal,
        decoded.issuance_id,
        signal_confidence,
        bit_error_rate,
        "decoded",
    )


def _mask_bits(
    key: bytes,
    nonce: bytes,
    page_index: int,
    candidate_id: bytes,
    bit_count: int,
) -> NDArray[np.uint8]:
    byte_count = (bit_count + 7) // 8
    stream = bytearray()
    counter = 0
    binding = nonce + page_index.to_bytes(4, "big") + candidate_id
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


def _luminance(
    page: PageImage, algorithm: _AlgorithmSettings
) -> NDArray[np.float64]:
    source = page.astype(np.float64)
    blue, green, red = algorithm.luminance_coefficients
    return blue * source[..., 0] + green * source[..., 1] + red * source[..., 2]


def _replace_luminance(
    page: PageImage,
    original: NDArray[np.float64],
    modified: NDArray[np.float64],
    algorithm: _AlgorithmSettings,
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
        algorithm.luminance_coefficients, dtype=np.float64
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
    algorithm = _validate_fixed_contract(contract)
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
    if sync_template is not None:
        sync_template = validate_sync_template(sync_template)
    return _RuntimeProfile(
        schema_version=int(version),
        qim_delta=float(values["qim_delta"]),
        tile_size_px=int(values["tile_size_px"]),
        tiles_per_page=int(values["tiles_per_page"]),
        payload_repetitions=repetitions,
        document_nonce=nonce,
        page_index=page_index,
        sync_template=sync_template,
        algorithm=algorithm,
        candidate_id=_candidate_identifier_from_values(
            int(version),
            float(values["qim_delta"]),
            int(values["tile_size_px"]),
            int(values["tiles_per_page"]),
            repetitions,
        ),
    )


def _candidate_identifier_from_values(
    schema_version: int,
    qim_delta: float,
    tile_size_px: int,
    tiles_per_page: int,
    payload_repetitions: int,
) -> bytes:
    return _CANDIDATE_ID_MARKER + struct.pack(
        ">IdIII",
        schema_version,
        qim_delta,
        tile_size_px,
        tiles_per_page,
        payload_repetitions,
    )


def _validate_fixed_contract(contract: Mapping[str, object]) -> _AlgorithmSettings:
    fixed = contract.get("fixed")
    if not isinstance(fixed, Mapping):
        raise ValueError("fingerprint fixed contract must be a mapping")
    exact_values = {
        "wavelet": "haar",
        "wavelet_level": 1,
        "detail_band": "HL",
        "transform_dtype": "float64",
        "dct_block_size": 8,
        "dct_transform": "orthonormal-dct-ii",
        "qim_rounding": "ties-to-even",
        "sync_detector": "orb-ransac",
    }
    for name, expected in exact_values.items():
        if fixed.get(name) != expected:
            raise ValueError(f"unsupported fingerprint fixed contract {name}")

    payload = payload_profile()
    if fixed.get("ecc_parity_symbols") != payload["reed_solomon"]["parity_symbols"]:
        raise ValueError("fingerprint ECC parity does not match the payload contract")
    if fixed.get("interleave_depth") != payload["interleave_depth"]:
        raise ValueError("fingerprint interleave depth does not match the payload contract")
    if fixed.get("luminance") != {
        "channel_order": "BGR",
        "standard": "BT.601-full-range",
        "coefficients": [0.114, 0.587, 0.299],
    }:
        raise ValueError("unsupported fingerprint fixed contract luminance")
    if fixed.get("padding") != {
        "mode": "edge",
        "edges": ["bottom", "right"],
        "inverse_crop": "original-shape",
    }:
        raise ValueError("unsupported fingerprint fixed contract padding")
    if fixed.get("raster") != {
        "input_dtypes": ["uint8", "uint16"],
        "rounding": "nearest-bt601-floor-ceil-combination",
        "clipping": "original-unsigned-depth",
    }:
        raise ValueError("unsupported fingerprint fixed contract raster")

    raw_pairs = fixed.get("midband_pairs")
    if raw_pairs != [
        [[1, 2], [2, 1]],
        [[2, 3], [3, 2]],
    ]:
        raise ValueError("unsupported fingerprint fixed contract midband_pairs")
    try:
        pairs = tuple(
            (
                (int(raw_pair[0][0]), int(raw_pair[0][1])),
                (int(raw_pair[1][0]), int(raw_pair[1][1])),
            )
            for raw_pair in raw_pairs
        )
    except (IndexError, TypeError, ValueError) as error:
        raise ValueError("fingerprint midband_pairs are malformed") from error
    if any(
        not 0 <= coordinate < exact_values["dct_block_size"]
        for pair in pairs
        for point in pair
        for coordinate in point
    ):
        raise ValueError("fingerprint midband_pairs exceed the DCT block")
    coefficients = fixed["luminance"]["coefficients"]
    return _AlgorithmSettings(
        block_size=exact_values["dct_block_size"],
        coefficient_pairs=pairs,
        luminance_coefficients=tuple(float(value) for value in coefficients),
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
