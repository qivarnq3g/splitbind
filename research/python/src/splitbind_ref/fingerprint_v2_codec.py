"""Replicated LL-DCT-QIM payload codec for fingerprint V2 tiles."""

from __future__ import annotations

import hashlib
import hmac
import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from .dwt_dct_qim import dct2, haar_dwt2, haar_idwt2, idct2, qim_embed_pair, qim_extract_pair
from .fingerprint_v2_profile import FingerprintV2Profile, candidate_identifier_v2


_CODEWORD_BYTES = 39
_BITS_PER_BYTE = 8
_COEFFICIENT_PAIRS = (((1, 2), (2, 1)), ((2, 3), (3, 2)))
_PERMUTATION_SEED_DOMAIN = b"splitbind-v2-payload-permutation\x00"
_PERMUTATION_STREAM_DOMAIN = b"splitbind-v2-payload-stream\x00"


@dataclass(frozen=True, slots=True)
class CodewordEvidence:
    codeword: bytes
    erase_positions: tuple[int, ...]
    mean_confidence: float
    bit_error_hint: float | None


def embed_codeword_v2(
    tile_luminance: NDArray[np.float64],
    codeword: bytes,
    key: bytes,
    page_index: int,
    profile: FingerprintV2Profile,
) -> NDArray[np.float64]:
    """Embed one interleaved V1 ECC codeword into a V2 tile's LL band."""

    tile = _validate_tile(tile_luminance, profile)
    _validate_codeword(codeword)
    _validate_binding(key, page_index, profile)
    bits = np.unpackbits(np.frombuffer(codeword, dtype=np.uint8), bitorder="big")
    replicated_bits = np.repeat(bits, profile.bit_replication)
    positions = _selected_positions(key, page_index, profile)
    if replicated_bits.size != len(positions):
        raise ValueError("V2 profile replication does not match payload capacity")

    ll, lh, hl, hh, original_shape = haar_dwt2(tile)
    embedded_ll = ll.copy()
    for bit, position in zip(replicated_bits, positions, strict=True):
        y, x, first, second = _position_components(position, profile)
        coefficients = dct2(embedded_ll[y : y + 8, x : x + 8])
        a, b = qim_embed_pair(
            coefficients[first], coefficients[second], int(bit), profile.qim_delta
        )
        coefficients[first] = a
        coefficients[second] = b
        embedded_ll[y : y + 8, x : x + 8] = idct2(coefficients)
    return haar_idwt2(embedded_ll, lh, hl, hh, original_shape)


def extract_codeword_v2(
    tile_luminance: NDArray[np.float64],
    key: bytes,
    page_index: int,
    profile: FingerprintV2Profile,
) -> CodewordEvidence:
    """Extract an interleaved codeword and its byte erasures from one V2 tile."""

    tile = _validate_tile(tile_luminance, profile)
    _validate_binding(key, page_index, profile)
    ll, _, _, _, _ = haar_dwt2(tile)
    positions = _selected_positions(key, page_index, profile)
    replica_bits = np.empty(len(positions), dtype=np.uint8)
    replica_confidences = np.empty(len(positions), dtype=np.float64)
    for index, position in enumerate(positions):
        y, x, first, second = _position_components(position, profile)
        coefficients = dct2(ll[y : y + 8, x : x + 8])
        extraction = qim_extract_pair(coefficients[first], coefficients[second], profile.qim_delta)
        replica_bits[index] = extraction.bit
        replica_confidences[index] = extraction.confidence

    bit_count = _CODEWORD_BYTES * _BITS_PER_BYTE
    recovered_bits = np.empty(bit_count, dtype=np.uint8)
    erasures: set[int] = set()
    confidence_sum = 0.0
    disagreement_sum = 0
    for bit_index in range(bit_count):
        start = bit_index * profile.bit_replication
        stop = start + profile.bit_replication
        values = replica_bits[start:stop]
        weights = replica_confidences[start:stop]
        zero_weight = float(weights[values == 0].sum())
        one_weight = float(weights[values == 1].sum())
        winner = 1 if one_weight > zero_weight else 0
        winning_confidence = max(zero_weight, one_weight) / profile.bit_replication
        recovered_bits[bit_index] = winner
        confidence_sum += winning_confidence
        disagreement_sum += int(np.count_nonzero(values != winner))
        if winning_confidence < profile.bit_confidence_min:
            erasures.add(bit_index // _BITS_PER_BYTE)

    return CodewordEvidence(
        codeword=np.packbits(recovered_bits, bitorder="big").tobytes(),
        erase_positions=tuple(sorted(erasures)),
        mean_confidence=confidence_sum / bit_count,
        bit_error_hint=disagreement_sum / len(replica_bits),
    )


def _capacity(profile: FingerprintV2Profile) -> int:
    return 2 * (profile.tile_size_px // 16) ** 2


def _selected_positions(
    key: bytes, page_index: int, profile: FingerprintV2Profile
) -> tuple[int, ...]:
    _validate_binding(key, page_index, profile)
    required = _CODEWORD_BYTES * _BITS_PER_BYTE * profile.bit_replication
    capacity = _capacity(profile)
    if required > capacity:
        raise ValueError(f"V2 tile capacity is {capacity} bits, but embedding needs {required}")
    values = list(range(capacity))
    seed_message = (
        _PERMUTATION_SEED_DOMAIN
        + page_index.to_bytes(4, "big")
        + candidate_identifier_v2(profile)
    )
    seed = hmac.new(key, seed_message, hashlib.sha256).digest()
    _shuffle(values, _HmacByteStream(seed))

    selected: list[int] = []
    bit_count = _CODEWORD_BYTES * _BITS_PER_BYTE
    pair_count = len(_COEFFICIENT_PAIRS)
    for _ in range(bit_count):
        replica_indices: list[int] = []
        replica_blocks: set[int] = set()
        for index, position in enumerate(values):
            block_index = position // pair_count
            if block_index in replica_blocks:
                continue
            replica_indices.append(index)
            replica_blocks.add(block_index)
            if len(replica_indices) == profile.bit_replication:
                break
        if len(replica_indices) != profile.bit_replication:
            raise ValueError("V2 tile cannot place replicas in distinct DCT blocks")
        selected.extend(values[index] for index in replica_indices)
        for index in reversed(replica_indices):
            del values[index]
    return tuple(selected)


def _position_components(
    position: int, profile: FingerprintV2Profile
) -> tuple[int, int, tuple[int, int], tuple[int, int]]:
    pair_count = len(_COEFFICIENT_PAIRS)
    block_index, pair_index = divmod(position, pair_count)
    blocks_per_edge = profile.tile_size_px // 16
    block_y, block_x = divmod(block_index, blocks_per_edge)
    first, second = _COEFFICIENT_PAIRS[pair_index]
    return block_y * 8, block_x * 8, first, second


class _HmacByteStream:
    def __init__(self, seed: bytes) -> None:
        self._seed = seed
        self._counter = 0
        self._buffer = bytearray()

    def randbelow(self, upper_bound: int) -> int:
        byte_count = max(1, (upper_bound.bit_length() + 7) // 8)
        sample_space = 1 << (byte_count * 8)
        acceptance_limit = sample_space - sample_space % upper_bound
        while True:
            candidate = int.from_bytes(self._read(byte_count), "big")
            if candidate < acceptance_limit:
                return candidate % upper_bound

    def _read(self, count: int) -> bytes:
        while len(self._buffer) < count:
            message = _PERMUTATION_STREAM_DOMAIN + self._counter.to_bytes(4, "big")
            self._buffer.extend(hmac.new(self._seed, message, hashlib.sha256).digest())
            self._counter += 1
        value = bytes(self._buffer[:count])
        del self._buffer[:count]
        return value


def _shuffle(values: list[int], rng: _HmacByteStream) -> None:
    for index in range(len(values) - 1, 0, -1):
        replacement = rng.randbelow(index + 1)
        values[index], values[replacement] = values[replacement], values[index]


def _validate_tile(
    tile_luminance: NDArray[np.float64], profile: FingerprintV2Profile
) -> NDArray[np.float64]:
    _validate_profile(profile)
    if not isinstance(tile_luminance, np.ndarray):
        raise TypeError("tile_luminance must be a numpy array")
    if tile_luminance.dtype != np.float64:
        raise TypeError("tile_luminance must have float64 dtype")
    if tile_luminance.ndim != 2:
        raise ValueError("tile_luminance must be two-dimensional")
    expected_shape = (profile.tile_size_px, profile.tile_size_px)
    if tile_luminance.shape != expected_shape:
        raise ValueError(f"tile_luminance must have contracted shape {expected_shape}")
    if not np.isfinite(tile_luminance).all():
        raise ValueError("tile_luminance must contain only finite values")
    return tile_luminance


def _validate_codeword(codeword: bytes) -> None:
    if not isinstance(codeword, bytes):
        raise TypeError("codeword must be bytes")
    if len(codeword) != _CODEWORD_BYTES:
        raise ValueError(f"codeword must contain exactly {_CODEWORD_BYTES} bytes")


def _validate_binding(key: bytes, page_index: int, profile: FingerprintV2Profile) -> None:
    if not isinstance(key, bytes) or not key:
        raise ValueError("key must be non-empty bytes")
    if (
        not isinstance(page_index, int)
        or isinstance(page_index, bool)
        or not 0 <= page_index <= 0xFFFFFFFF
    ):
        raise ValueError("page_index must fit an unsigned 32-bit integer")
    _validate_profile(profile)


def _validate_profile(profile: FingerprintV2Profile) -> None:
    if type(profile) is not FingerprintV2Profile:
        raise TypeError("profile must be a FingerprintV2Profile")
    if profile.schema_version != 2:
        raise ValueError("profile schema_version must be 2")
    if profile.tile_size_px <= 0 or profile.tile_size_px % 16:
        raise ValueError("profile tile_size_px must be a positive multiple of 16")
    if profile.bit_replication != 3:
        raise ValueError("profile bit_replication must be the frozen value 3")
    if profile.bit_confidence_min != 0.60:
        raise ValueError("profile bit_confidence_min must be the frozen value 0.60")
    if not math.isfinite(profile.qim_delta) or profile.qim_delta <= 0.0:
        raise ValueError("profile qim_delta must be finite and positive")
    candidate_identifier_v2(profile)
