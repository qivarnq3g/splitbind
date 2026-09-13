"""Saturation-safe spread codec for the frozen V3 research candidates."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from .ecc import rank_erasure_candidates
from .fingerprint_v3_profile import FingerprintV3Profile, candidate_identifier_v3


_CODEWORD_BYTES = 39
_BITS_PER_BYTE = 8
_CHIP_SEED_DOMAIN = b"splitbind-v3-spread-chip-permutation\x00"
_CHIP_STREAM_DOMAIN = b"splitbind-v3-spread-chip-stream\x00"


@dataclass(frozen=True, slots=True)
class SpreadCodewordEvidence:
    codeword: bytes
    erase_positions: tuple[int, ...]
    mean_confidence: float
    polarity: Literal["darken", "lighten"]
    erasure_ranking: tuple[int, ...] = ()


def embed_spread_codeword_v3(
    tile_luminance: NDArray[np.float64],
    codeword: bytes,
    key: bytes,
    page_index: int,
    profile: FingerprintV3Profile,
) -> NDArray[np.float64]:
    """Embed one ECC codeword by changing only the available saturation direction."""

    tile = _validate_tile(tile_luminance, profile)
    _validate_codeword(codeword)
    groups = _chip_groups(key, page_index, profile)
    bits = np.unpackbits(np.frombuffer(codeword, dtype=np.uint8), bitorder="big")
    polarity = _embedding_polarity(tile)
    embedded = tile.copy()
    samples = embedded.reshape(-1)
    for bit, (group_a, group_b) in zip(bits, groups, strict=True):
        active = group_b if bit else group_a
        if polarity == "darken":
            samples[list(active)] = np.maximum(
                0.0, samples[list(active)] - profile.spread_delta
            )
        else:
            samples[list(active)] = np.minimum(
                255.0, samples[list(active)] + profile.spread_delta
            )
    return embedded


def extract_spread_codeword_v3(
    tile_luminance: NDArray[np.float64],
    key: bytes,
    page_index: int,
    profile: FingerprintV3Profile,
    polarity: Literal["darken", "lighten"],
) -> SpreadCodewordEvidence:
    """Extract a spread codeword and mark bytes containing weak bits as erasures."""

    tile = _validate_tile(tile_luminance, profile)
    if polarity not in ("darken", "lighten"):
        raise ValueError("polarity must be 'darken' or 'lighten'")
    groups = _chip_groups(key, page_index, profile)
    samples = tile.reshape(-1)
    bits = np.empty(_CODEWORD_BYTES * _BITS_PER_BYTE, dtype=np.uint8)
    erasures: set[int] = set()
    byte_confidence = np.full(_CODEWORD_BYTES, np.inf, dtype=np.float64)
    confidence_sum = 0.0
    for bit_index, (group_a, group_b) in enumerate(groups):
        difference = float(np.mean(samples[list(group_a)]) - np.mean(samples[list(group_b)]))
        if polarity == "darken":
            bits[bit_index] = 1 if difference > 0.0 else 0
        else:
            bits[bit_index] = 0 if difference > 0.0 else 1
        confidence = min(1.0, abs(difference) / profile.spread_delta)
        confidence_sum += confidence
        byte_index = bit_index // _BITS_PER_BYTE
        byte_confidence[byte_index] = min(byte_confidence[byte_index], confidence)
        if confidence < profile.bit_confidence_min:
            erasures.add(byte_index)

    return SpreadCodewordEvidence(
        codeword=np.packbits(bits, bitorder="big").tobytes(),
        erase_positions=tuple(sorted(erasures)),
        mean_confidence=confidence_sum / len(bits),
        polarity=polarity,
        erasure_ranking=rank_erasure_candidates(byte_confidence),
    )


def _chip_groups(
    key: bytes, page_index: int, profile: FingerprintV3Profile
) -> tuple[tuple[tuple[int, ...], tuple[int, ...]], ...]:
    """Return deterministic, disjoint complementary chip groups for every bit."""

    _validate_binding(key, page_index, profile)
    bit_count = _CODEWORD_BYTES * _BITS_PER_BYTE
    chips_per_block = 16
    if profile.spread_chips_per_bit % chips_per_block:
        raise ValueError("V3 spread chips per bit must be divisible by 16")
    blocks_per_bit = profile.spread_chips_per_bit // chips_per_block
    blocks_per_edge = profile.tile_size_px // 8
    block_capacity = blocks_per_edge**2
    required_blocks = bit_count * blocks_per_bit
    if required_blocks > block_capacity:
        raise ValueError(
            f"V3 spread capacity is {block_capacity} carrier blocks, but embedding needs "
            f"{required_blocks}"
        )

    block_indexes = list(range(block_capacity))
    seed_message = (
        _CHIP_SEED_DOMAIN
        + page_index.to_bytes(4, "big")
        + candidate_identifier_v3(profile)
    )
    stream = _HmacByteStream(hmac.new(key, seed_message, hashlib.sha256).digest())
    _shuffle(block_indexes, stream)
    selected = block_indexes[:required_blocks]
    groups = []
    for bit_index in range(bit_count):
        start = bit_index * blocks_per_bit
        block_slice = selected[start : start + blocks_per_bit]
        group_a = []
        group_b = []
        for block_index in block_slice:
            block_y, block_x = divmod(block_index, blocks_per_edge)
            origin_y = block_y * 8
            origin_x = block_x * 8
            orientation = stream.randbelow(4)
            first_x = origin_x + (4 if orientation >= 2 else 0)
            first_y = origin_y
            second_x = origin_x + (0 if orientation >= 2 else 4)
            second_y = origin_y + 4
            first = tuple(
                y * profile.tile_size_px + x
                for y in range(first_y, first_y + 4)
                for x in range(first_x, first_x + 4)
            )
            second = tuple(
                y * profile.tile_size_px + x
                for y in range(second_y, second_y + 4)
                for x in range(second_x, second_x + 4)
            )
            if orientation % 2:
                first, second = second, first
            group_a.extend(first)
            group_b.extend(second)
        groups.append((tuple(group_a), tuple(group_b)))
    return tuple(groups)


def _embedding_polarity(tile: NDArray[np.float64]) -> Literal["darken", "lighten"]:
    return "darken" if float(np.mean(tile)) >= 127.5 else "lighten"


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
            message = _CHIP_STREAM_DOMAIN + self._counter.to_bytes(4, "big")
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
    tile_luminance: NDArray[np.float64], profile: FingerprintV3Profile
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
    if np.any(tile_luminance < 0.0) or np.any(tile_luminance > 255.0):
        raise ValueError("tile_luminance samples must be in the interval [0, 255]")
    return tile_luminance


def _validate_codeword(codeword: bytes) -> None:
    if not isinstance(codeword, bytes):
        raise TypeError("codeword must be bytes")
    if len(codeword) != _CODEWORD_BYTES:
        raise ValueError(f"codeword must contain exactly {_CODEWORD_BYTES} bytes")


def _validate_binding(key: bytes, page_index: int, profile: FingerprintV3Profile) -> None:
    if not isinstance(key, bytes) or not key:
        raise ValueError("key must be non-empty bytes")
    if (
        not isinstance(page_index, int)
        or isinstance(page_index, bool)
        or not 0 <= page_index <= 0xFFFFFFFF
    ):
        raise ValueError("page_index must fit an unsigned 32-bit integer")
    _validate_profile(profile)


def _validate_profile(profile: FingerprintV3Profile) -> None:
    if type(profile) is not FingerprintV3Profile:
        raise TypeError("profile must be a FingerprintV3Profile")
    candidate_identifier_v3(profile)
