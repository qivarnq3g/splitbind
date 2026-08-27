"""Deterministic, key-bound placement of non-overlapping fingerprint tiles."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Mapping

from .contracts import fingerprint_candidates


_PERMUTATION_DOMAIN = b"splitbind-tile-permutation\x00"


@dataclass(frozen=True, slots=True)
class Tile:
    x: int
    y: int
    width: int
    height: int


def derive_tiles(
    page_shape: tuple[int, int],
    key: bytes,
    document_nonce: bytes,
    page_index: int,
    profile: Mapping[str, int],
) -> tuple[Tile, ...]:
    """Return tiles for a ``(height, width)`` page shape."""

    height, width = _validate_page_shape(page_shape)
    _validate_bytes("key", key)
    _validate_bytes("document nonce", document_nonce)
    if (
        not isinstance(page_index, int)
        or isinstance(page_index, bool)
        or not 0 <= page_index <= 0xFFFFFFFF
    ):
        raise ValueError("page_index must fit an unsigned 32-bit integer")

    version, tile_size, tile_count = _validate_profile(profile)
    if tile_size > height or tile_size > width:
        raise ValueError("page is smaller than the contracted tile size")

    candidates = [
        Tile(x=x, y=y, width=tile_size, height=tile_size)
        for y in range(0, height - tile_size + 1, tile_size)
        for x in range(0, width - tile_size + 1, tile_size)
    ]
    if tile_count > len(candidates):
        raise ValueError(
            f"page provides {len(candidates)} non-overlapping tile slots, "
            f"but profile requests {tile_count}"
        )

    seed_message = (
        document_nonce
        + page_index.to_bytes(4, "big")
        + version.to_bytes(4, "big")
    )
    seed = hmac.new(key, seed_message, hashlib.sha256).digest()
    rng = _HmacByteStream(seed)
    _shuffle(candidates, rng)
    return tuple(candidates[:tile_count])


class _HmacByteStream:
    def __init__(self, seed: bytes) -> None:
        self._seed = seed
        self._counter = 0
        self._buffer = bytearray()

    def randbelow(self, upper_bound: int) -> int:
        if upper_bound <= 0:
            raise ValueError("upper_bound must be positive")
        byte_count = max(1, (upper_bound.bit_length() + 7) // 8)
        sample_space = 1 << (byte_count * 8)
        acceptance_limit = sample_space - sample_space % upper_bound
        while True:
            candidate = int.from_bytes(self._read(byte_count), "big")
            if candidate < acceptance_limit:
                return candidate % upper_bound

    def _read(self, count: int) -> bytes:
        while len(self._buffer) < count:
            message = _PERMUTATION_DOMAIN + self._counter.to_bytes(4, "big")
            self._buffer.extend(hmac.new(self._seed, message, hashlib.sha256).digest())
            self._counter += 1
        value = bytes(self._buffer[:count])
        del self._buffer[:count]
        return value


def _shuffle(values: list[Tile], rng: _HmacByteStream) -> None:
    for index in range(len(values) - 1, 0, -1):
        replacement = rng.randbelow(index + 1)
        values[index], values[replacement] = values[replacement], values[index]


def _validate_page_shape(page_shape: tuple[int, int]) -> tuple[int, int]:
    if not isinstance(page_shape, (tuple, list)) or len(page_shape) != 2:
        raise ValueError("page_shape must contain height and width")
    height, width = page_shape
    if any(
        not isinstance(value, int) or isinstance(value, bool) or value <= 0
        for value in (height, width)
    ):
        raise ValueError("page dimensions must be positive integers")
    return height, width


def _validate_bytes(name: str, value: bytes) -> None:
    if not isinstance(value, bytes) or not value:
        raise ValueError(f"{name} must be non-empty bytes")


def _validate_profile(profile: Mapping[str, int]) -> tuple[int, int, int]:
    required = {"schema_version", "tile_size_px", "tiles_per_page"}
    if not isinstance(profile, Mapping) or set(profile) != required:
        raise ValueError(f"profile must contain exactly {sorted(required)}")

    contract = fingerprint_candidates()
    version = profile["schema_version"]
    tile_size = profile["tile_size_px"]
    tile_count = profile["tiles_per_page"]
    if version != contract["schema_version"]:
        raise ValueError("unsupported profile schema_version")
    if tile_size not in contract["sweep"]["tile_size_px"]:
        raise ValueError("tile_size_px is not in the contracted candidate grid")
    if tile_count not in contract["sweep"]["tiles_per_page"]:
        raise ValueError("tiles_per_page is not in the contracted candidate grid")
    return version, tile_size, tile_count
