"""Deterministic Haar, orthonormal DCT, and parity-QIM primitives.

All transforms accept and return two-dimensional ``float64`` arrays.  Haar
padding repeats the final row or column to reach an even shape and the inverse
crops to the recorded original shape.  QIM lattice selection uses Python's
ties-to-even ``round`` operation, matching the version-1 reference contract.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import cache

import numpy as np
from numpy.typing import NDArray


FloatImage = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class QimExtraction:
    bit: int
    lattice_index: int
    confidence: float


def haar_dwt2(
    image: FloatImage,
) -> tuple[FloatImage, FloatImage, FloatImage, FloatImage, tuple[int, int]]:
    """Apply one orthonormal two-dimensional Haar analysis level."""

    source = _validate_float64_image(image)
    original_shape = source.shape
    pad_rows = original_shape[0] % 2
    pad_columns = original_shape[1] % 2
    if pad_rows or pad_columns:
        source = np.pad(source, ((0, pad_rows), (0, pad_columns)), mode="edge")

    scale = math.sqrt(2.0)
    horizontal_low = (source[:, 0::2] + source[:, 1::2]) / scale
    horizontal_high = (source[:, 0::2] - source[:, 1::2]) / scale
    ll = (horizontal_low[0::2, :] + horizontal_low[1::2, :]) / scale
    lh = (horizontal_low[0::2, :] - horizontal_low[1::2, :]) / scale
    hl = (horizontal_high[0::2, :] + horizontal_high[1::2, :]) / scale
    hh = (horizontal_high[0::2, :] - horizontal_high[1::2, :]) / scale
    return ll, lh, hl, hh, original_shape


def haar_idwt2(
    ll: FloatImage,
    lh: FloatImage,
    hl: FloatImage,
    hh: FloatImage,
    original_shape: tuple[int, int],
) -> FloatImage:
    """Invert one Haar level and remove the recorded edge padding."""

    bands = tuple(_validate_float64_image(band) for band in (ll, lh, hl, hh))
    if any(band.shape != bands[0].shape for band in bands[1:]):
        raise ValueError("Haar bands must have identical shapes")
    if (
        not isinstance(original_shape, tuple)
        or len(original_shape) != 2
        or any(not isinstance(value, int) or value <= 0 for value in original_shape)
    ):
        raise ValueError("original_shape must contain two positive integers")

    scale = math.sqrt(2.0)
    horizontal_low = np.empty((ll.shape[0] * 2, ll.shape[1]), dtype=np.float64)
    horizontal_high = np.empty_like(horizontal_low)
    horizontal_low[0::2, :] = (ll + lh) / scale
    horizontal_low[1::2, :] = (ll - lh) / scale
    horizontal_high[0::2, :] = (hl + hh) / scale
    horizontal_high[1::2, :] = (hl - hh) / scale

    restored = np.empty(
        (horizontal_low.shape[0], horizontal_low.shape[1] * 2), dtype=np.float64
    )
    restored[:, 0::2] = (horizontal_low + horizontal_high) / scale
    restored[:, 1::2] = (horizontal_low - horizontal_high) / scale
    height, width = original_shape
    if height > restored.shape[0] or width > restored.shape[1]:
        raise ValueError("original_shape exceeds the reconstructed padded image")
    return restored[:height, :width]


def dct2(block: FloatImage) -> FloatImage:
    """Return the orthonormal DCT-II of one 8x8 block."""

    source = _validate_dct_block(block)
    transform = _dct_matrix()
    return transform @ source @ transform.T


def idct2(coefficients: FloatImage) -> FloatImage:
    """Return the orthonormal inverse DCT of one 8x8 coefficient block."""

    source = _validate_dct_block(coefficients)
    transform = _dct_matrix()
    return transform.T @ source @ transform


def qim_embed_pair(
    a: float, b: float, bit: int, delta: float
) -> tuple[float, float]:
    """Move a coefficient difference onto the requested parity lattice."""

    _validate_qim_inputs(a, b, delta)
    if not isinstance(bit, int) or isinstance(bit, bool) or bit not in (0, 1):
        raise ValueError("bit must be 0 or 1")
    difference = float(a) - float(b)
    lattice = round(difference / float(delta))
    target = lattice if lattice % 2 == bit else lattice + 1
    correction = (target * float(delta) - difference) / 2.0
    return float(a) + correction, float(b) - correction


def qim_extract_pair(a: float, b: float, delta: float) -> QimExtraction:
    """Read a parity bit and a bounded distance confidence from a pair."""

    _validate_qim_inputs(a, b, delta)
    normalized = (float(a) - float(b)) / float(delta)
    lattice = round(normalized)
    distance = abs(normalized - lattice)
    confidence = max(0.0, min(1.0, 1.0 - 2.0 * distance))
    return QimExtraction(
        bit=lattice % 2,
        lattice_index=lattice,
        confidence=confidence,
    )


def embed_bits_in_band(
    detail_band: FloatImage,
    bits: NDArray[np.uint8],
    coefficient_pairs: tuple[tuple[tuple[int, int], tuple[int, int]], ...],
    delta: float,
) -> FloatImage:
    """Embed bits block-major/pair-major into one 8x8-partitioned detail band."""

    band = _validate_float64_image(detail_band)
    if not isinstance(bits, np.ndarray) or bits.ndim != 1 or bits.dtype != np.uint8:
        raise TypeError("bits must be a one-dimensional uint8 array")
    if np.any((bits != 0) & (bits != 1)):
        raise ValueError("bits must contain only 0 or 1")
    pairs = _validate_coefficient_pairs(coefficient_pairs)
    capacity = (band.shape[0] // 8) * (band.shape[1] // 8) * len(pairs)
    if bits.size > capacity:
        raise ValueError(
            f"detail-band capacity is {capacity} bits, but embedding needs {bits.size}"
        )

    embedded = band.copy()
    bit_index = 0
    for y in range(0, embedded.shape[0] - 7, 8):
        for x in range(0, embedded.shape[1] - 7, 8):
            coefficients = dct2(embedded[y : y + 8, x : x + 8])
            for first, second in pairs:
                if bit_index >= bits.size:
                    break
                a, b = qim_embed_pair(
                    coefficients[first],
                    coefficients[second],
                    int(bits[bit_index]),
                    delta,
                )
                coefficients[first] = a
                coefficients[second] = b
                bit_index += 1
            embedded[y : y + 8, x : x + 8] = idct2(coefficients)
            if bit_index >= bits.size:
                break
        if bit_index >= bits.size:
            break
    return embedded


@cache
def _dct_matrix() -> FloatImage:
    size = 8
    matrix = np.empty((size, size), dtype=np.float64)
    for frequency in range(size):
        scale = math.sqrt(1.0 / size) if frequency == 0 else math.sqrt(2.0 / size)
        for position in range(size):
            matrix[frequency, position] = scale * math.cos(
                math.pi * (2 * position + 1) * frequency / (2 * size)
            )
    matrix.setflags(write=False)
    return matrix


def _validate_float64_image(image: FloatImage) -> FloatImage:
    if not isinstance(image, np.ndarray):
        raise TypeError("transform input must be a numpy array")
    if image.ndim != 2:
        raise ValueError("transform input must be two-dimensional")
    if image.dtype != np.float64:
        raise TypeError("transform input dtype must be float64")
    if not np.isfinite(image).all():
        raise ValueError("transform input must contain only finite values")
    return image


def _validate_dct_block(block: FloatImage) -> FloatImage:
    source = _validate_float64_image(block)
    if source.shape != (8, 8):
        raise ValueError("DCT input must be exactly 8x8")
    return source


def _validate_qim_inputs(a: float, b: float, delta: float) -> None:
    values = (a, b, delta)
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
        raise TypeError("QIM coefficients and delta must be real numbers")
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("QIM coefficients and delta must be finite")
    if float(delta) <= 0.0:
        raise ValueError("delta must be positive")


def _validate_coefficient_pairs(
    pairs: tuple[tuple[tuple[int, int], tuple[int, int]], ...],
) -> tuple[tuple[tuple[int, int], tuple[int, int]], ...]:
    if not isinstance(pairs, tuple) or not pairs:
        raise ValueError("coefficient_pairs must be a non-empty tuple")
    for pair in pairs:
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise ValueError("each coefficient pair must contain two coordinates")
        for coordinate in pair:
            if (
                not isinstance(coordinate, tuple)
                or len(coordinate) != 2
                or any(
                    not isinstance(value, int) or isinstance(value, bool) or not 0 <= value < 8
                    for value in coordinate
                )
            ):
                raise ValueError("coefficient coordinates must be integer 8x8 indices")
    return pairs
