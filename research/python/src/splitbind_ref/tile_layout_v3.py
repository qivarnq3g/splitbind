"""Nonce-independent, key-bound placement of V3 fingerprint tiles."""

from __future__ import annotations

import hashlib
import hmac

from .fingerprint_v3_profile import FingerprintV3Profile, candidate_identifier_v3
from .tile_layout import Tile


_MAX_PAGE_PIXELS = 40_000_000
_SEED_DOMAIN = b"splitbind-v3-tile-layout\x00"
_STREAM_DOMAIN = b"splitbind-v3-tile-permutation\x00"


def derive_tiles_v3(
    page_shape: tuple[int, int],
    key: bytes,
    page_index: int,
    profile: FingerprintV3Profile,
) -> tuple[Tile, ...]:
    """Return the V3 tiles for a page without requiring a document nonce."""

    height, width = _validate_page_shape(page_shape)
    _validate_key(key)
    _validate_page_index(page_index)
    _validate_profile(profile)
    if height * width > _MAX_PAGE_PIXELS:
        raise ValueError("page exceeds the 40-megapixel processing ceiling")
    if profile.tile_size_px > height or profile.tile_size_px > width:
        raise ValueError("page is smaller than the contracted tile size")

    candidates = [
        Tile(x=x, y=y, width=profile.tile_size_px, height=profile.tile_size_px)
        for y in range(0, height - profile.tile_size_px + 1, profile.tile_size_px)
        for x in range(0, width - profile.tile_size_px + 1, profile.tile_size_px)
    ]
    if profile.tiles_per_page > len(candidates):
        raise ValueError(
            f"page provides {len(candidates)} non-overlapping tile slots, "
            f"but profile requests {profile.tiles_per_page}"
        )

    seed_message = (
        _SEED_DOMAIN + page_index.to_bytes(4, "big") + candidate_identifier_v3(profile)
    )
    seed = hmac.new(key, seed_message, hashlib.sha256).digest()
    _shuffle(candidates, _HmacByteStream(seed))
    crop_survivors: list[Tile] = []
    crop_vulnerable: list[Tile] = []
    for tile in candidates:
        destination = (
            crop_survivors
            if _survives_center_crops(
                tile, height, width, profile.crop_retained_scales
            )
            else crop_vulnerable
        )
        destination.append(tile)
    candidates = crop_survivors + crop_vulnerable
    return tuple(candidates[: profile.tiles_per_page])


def _survives_center_crops(
    tile: Tile,
    page_height: int,
    page_width: int,
    retained_scales: tuple[float, ...],
) -> bool:
    for retained_scale in retained_scales:
        retained_height = round(page_height * retained_scale)
        retained_width = round(page_width * retained_scale)
        y0 = (page_height - retained_height) // 2
        x0 = (page_width - retained_width) // 2
        if not (
            x0 <= tile.x
            and y0 <= tile.y
            and tile.x + tile.width <= x0 + retained_width
            and tile.y + tile.height <= y0 + retained_height
        ):
            return False
    return True


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
            message = _STREAM_DOMAIN + self._counter.to_bytes(4, "big")
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


def _validate_key(key: bytes) -> None:
    if not isinstance(key, bytes) or not key:
        raise ValueError("key must be non-empty bytes")


def _validate_page_index(page_index: int) -> None:
    if (
        not isinstance(page_index, int)
        or isinstance(page_index, bool)
        or not 0 <= page_index <= 0xFFFFFFFF
    ):
        raise ValueError("page_index must fit an unsigned 32-bit integer")


def _validate_profile(profile: FingerprintV3Profile) -> None:
    if type(profile) is not FingerprintV3Profile:
        raise TypeError("profile must be a FingerprintV3Profile")
    if profile.schema_version != 3:
        raise ValueError("profile schema_version must be 3")
    if profile.tile_size_px <= 0 or profile.tiles_per_page <= 0:
        raise ValueError("profile tile dimensions and count must be positive")
    candidate_identifier_v3(profile)
