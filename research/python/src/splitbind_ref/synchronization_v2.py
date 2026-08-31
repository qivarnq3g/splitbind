"""Deterministic Fourier pilot synthesis and normalized V2 scoring."""

from __future__ import annotations

import hashlib
import hmac
import math
from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

from .fingerprint_v2_profile import FingerprintV2Profile, candidate_identifier_v2


_MAX_PAGE_PIXELS = 40_000_000
_PILOT_PAIR_COUNT = 12
_RADIUS_MIN = 0.08
_RADIUS_MAX = 0.18
_AXIS_CLEARANCE = 0.02
_PAIR_CLEARANCE = 0.015
_FFT_LONG_EDGE_MAX = 2048
_SEED_DOMAIN = b"splitbind-v2-sync-pilot\x00"
_STREAM_DOMAIN = b"splitbind-v2-sync-pilot-stream\x00"
_SYNTHESIS_ROW_CHUNK = 256


@dataclass(frozen=True, slots=True)
class PilotTemplateV2:
    """Immutable page-sized pilot and its normalized frequency constellation."""

    page_shape: tuple[int, int]
    frequency_pairs: NDArray[np.float64]
    spatial: NDArray[np.float64]

    def __post_init__(self) -> None:
        height, width = _validate_page_shape(self.page_shape)
        _validate_pixel_ceiling(height, width)
        if not isinstance(self.frequency_pairs, np.ndarray):
            raise TypeError("frequency_pairs must be a numpy array")
        if self.frequency_pairs.dtype != np.float64:
            raise TypeError("frequency_pairs must use float64")
        if self.frequency_pairs.shape != (_PILOT_PAIR_COUNT, 2):
            raise ValueError("frequency_pairs must have shape (12, 2)")
        if not np.isfinite(self.frequency_pairs).all():
            raise ValueError("frequency_pairs must contain only finite values")
        if not isinstance(self.spatial, np.ndarray):
            raise TypeError("spatial must be a numpy array")
        if self.spatial.dtype != np.float64:
            raise TypeError("spatial must use float64")
        if self.spatial.shape != (height, width):
            raise ValueError("spatial shape must match page_shape")
        if not np.isfinite(self.spatial).all():
            raise ValueError("spatial must contain only finite values")

        frequency_copy = np.array(
            self.frequency_pairs, dtype=np.float64, order="C", copy=True
        )
        spatial_copy = np.array(self.spatial, dtype=np.float64, order="C", copy=True)
        frequency_copy.setflags(write=False)
        spatial_copy.setflags(write=False)
        object.__setattr__(self, "page_shape", (height, width))
        object.__setattr__(self, "frequency_pairs", frequency_copy)
        object.__setattr__(self, "spatial", spatial_copy)


def synthesize_pilot_v2(
    page_shape: tuple[int, int],
    key: bytes,
    page_index: int,
    profile: FingerprintV2Profile,
) -> PilotTemplateV2:
    """Derive a key/page/profile-bound zero-mean, unit-RMS spatial pilot."""

    height, width = _validate_page_shape(page_shape)
    _validate_pixel_ceiling(height, width)
    _validate_key(key)
    _validate_page_index(page_index)
    _validate_profile(profile)

    domain = _SEED_DOMAIN + page_index.to_bytes(4, "big")
    seed = hmac.new(
        key, domain + candidate_identifier_v2(profile), hashlib.sha256
    ).digest()
    frequencies, phases, amplitudes = _derive_constellation(_HmacByteStream(seed))
    spatial = _synthesize_spatial(
        height, width, frequencies, phases, amplitudes
    )
    return PilotTemplateV2((height, width), frequencies, spatial)


def embed_pilot_v2(
    luminance: NDArray[np.generic],
    template: PilotTemplateV2,
    strength_rms: float,
) -> NDArray[np.float64]:
    """Add a pilot in float64 luminance space without clipping either endpoint."""

    height, width = _validate_luminance(luminance)
    _validate_pixel_ceiling(height, width)
    _validate_template(template)
    if (height, width) != template.page_shape:
        raise ValueError("luminance shape must match the pilot template shape")
    if (
        isinstance(strength_rms, (bool, np.bool_))
        or not isinstance(strength_rms, (int, float, np.integer, np.floating))
        or not math.isfinite(float(strength_rms))
        or float(strength_rms) < 0.0
    ):
        raise ValueError("strength_rms must be a finite non-negative real number")
    if not np.isfinite(luminance).all():
        raise ValueError("luminance must contain only finite values")

    result = luminance.astype(np.float64, copy=True)
    result += float(strength_rms) * template.spatial
    if not np.isfinite(result).all():
        raise ValueError("embedded pilot must contain only finite values")
    return np.ascontiguousarray(result, dtype=np.float64)


def score_pilot_v2(
    luminance: NDArray[np.generic], template: PilotTemplateV2
) -> float:
    """Return bounded normalized Fourier correlation with a canonical pilot."""

    height, width = _validate_luminance(luminance)
    _validate_pixel_ceiling(height, width)
    _validate_template(template)
    if (height, width) != template.page_shape:
        raise ValueError("luminance shape must match the pilot template shape")
    if not np.isfinite(luminance).all():
        raise ValueError("luminance must contain only finite values")

    scoring_view, template_view, sample_scale = _bounded_scoring_views(
        luminance, template.spatial
    )
    signal_fft = _windowed_rfft(scoring_view)
    template_fft = _windowed_rfft(template_view)
    pilot_band = _pilot_band_mask(scoring_view.shape, sample_scale)
    if not np.any(pilot_band):
        return 0.0
    template_values = template_fft[pilot_band]
    signal_values = signal_fft[pilot_band]
    if not np.isfinite(template_values).all() or not np.isfinite(signal_values).all():
        return 0.0
    template_energy = float(np.vdot(template_values, template_values).real)
    signal_energy = float(np.vdot(signal_values, signal_values).real)
    if template_energy <= 0.0 or signal_energy <= 0.0:
        return 0.0
    denominator = math.sqrt(template_energy * signal_energy)
    if not math.isfinite(denominator) or denominator <= 0.0:
        return 0.0
    score = float(np.vdot(template_values, signal_values).real / denominator)
    if not math.isfinite(score):
        return 0.0
    return float(np.clip(score, -1.0, 1.0))


class _HmacByteStream:
    def __init__(self, seed: bytes) -> None:
        self._seed = seed
        self._counter = 0
        self._buffer = bytearray()

    def uniform(self) -> float:
        integer = int.from_bytes(self._read(8), "big")
        return (integer + 0.5) / float(1 << 64)

    def _read(self, count: int) -> bytes:
        while len(self._buffer) < count:
            message = _STREAM_DOMAIN + self._counter.to_bytes(4, "big")
            self._buffer.extend(
                hmac.new(self._seed, message, hashlib.sha256).digest()
            )
            self._counter += 1
        value = bytes(self._buffer[:count])
        del self._buffer[:count]
        return value


def _derive_constellation(
    stream: _HmacByteStream,
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    frequencies: list[tuple[float, float]] = []
    phases: list[float] = []
    amplitudes: list[float] = []
    while len(frequencies) < _PILOT_PAIR_COUNT:
        frequency_x = (2.0 * stream.uniform() - 1.0) * _RADIUS_MAX
        frequency_y = (2.0 * stream.uniform() - 1.0) * _RADIUS_MAX
        radius = math.hypot(frequency_x, frequency_y)
        if not _RADIUS_MIN <= radius <= _RADIUS_MAX:
            continue
        if abs(frequency_x) < _AXIS_CLEARANCE or abs(frequency_y) < _AXIS_CLEARANCE:
            continue
        if frequency_x < 0.0:
            frequency_x = -frequency_x
            frequency_y = -frequency_y
        candidate = np.array((frequency_x, frequency_y), dtype=np.float64)
        if not _is_clear_asymmetric_candidate(candidate, frequencies):
            continue
        frequencies.append((frequency_x, frequency_y))
        phases.append(2.0 * math.pi * stream.uniform())
        amplitudes.append(0.85 + 0.30 * stream.uniform())
    return (
        np.asarray(frequencies, dtype=np.float64),
        np.asarray(phases, dtype=np.float64),
        np.asarray(amplitudes, dtype=np.float64),
    )


def _is_clear_asymmetric_candidate(
    candidate: NDArray[np.float64], accepted: list[tuple[float, float]]
) -> bool:
    reflected_candidate = candidate * np.array((1.0, -1.0), dtype=np.float64)
    for accepted_frequency in accepted:
        previous = np.asarray(accepted_frequency, dtype=np.float64)
        if np.linalg.norm(candidate - previous) < _PAIR_CLEARANCE:
            return False
        if np.linalg.norm(candidate + previous) < _PAIR_CLEARANCE:
            return False
        if np.linalg.norm(reflected_candidate - previous) < _PAIR_CLEARANCE:
            return False
    return True


def _synthesize_spatial(
    height: int,
    width: int,
    frequencies: NDArray[np.float64],
    phases: NDArray[np.float64],
    amplitudes: NDArray[np.float64],
) -> NDArray[np.float64]:
    x = np.arange(width, dtype=np.float64)
    spatial = np.zeros((height, width), dtype=np.float64)
    two_pi = 2.0 * math.pi
    for start in range(0, height, _SYNTHESIS_ROW_CHUNK):
        stop = min(height, start + _SYNTHESIS_ROW_CHUNK)
        y = np.arange(start, stop, dtype=np.float64)[:, None]
        chunk = spatial[start:stop]
        for (frequency_x, frequency_y), phase, amplitude in zip(
            frequencies, phases, amplitudes, strict=True
        ):
            angles = two_pi * (frequency_x * x[None, :] + frequency_y * y) + phase
            chunk += amplitude * np.cos(angles)
    spatial -= float(np.mean(spatial, dtype=np.float64))
    rms = float(np.sqrt(np.mean(spatial * spatial, dtype=np.float64)))
    if not math.isfinite(rms) or rms <= 0.0:
        raise ValueError("derived pilot has zero or non-finite energy")
    spatial /= rms
    return spatial


def _bounded_scoring_views(
    luminance: NDArray[np.generic], spatial: NDArray[np.float64]
) -> tuple[NDArray[np.float64], NDArray[np.float64], float]:
    height, width = luminance.shape
    long_edge = max(height, width)
    if long_edge <= _FFT_LONG_EDGE_MAX:
        return (
            np.ascontiguousarray(luminance, dtype=np.float64),
            np.ascontiguousarray(spatial, dtype=np.float64),
            1.0,
        )
    scale = _FFT_LONG_EDGE_MAX / long_edge
    resized_width = max(1, int(round(width * scale)))
    resized_height = max(1, int(round(height * scale)))
    size = (resized_width, resized_height)
    scoring_view = cv2.resize(
        luminance.astype(np.float64, copy=False), size, interpolation=cv2.INTER_AREA
    )
    template_view = cv2.resize(spatial, size, interpolation=cv2.INTER_AREA)
    return (
        np.ascontiguousarray(scoring_view, dtype=np.float64),
        np.ascontiguousarray(template_view, dtype=np.float64),
        scale,
    )


def _pilot_band_mask(shape: tuple[int, int], sample_scale: float) -> NDArray[np.bool_]:
    height, width = shape
    frequency_y = np.fft.fftfreq(height)[:, None]
    frequency_x = np.fft.rfftfreq(width)[None, :]
    original_radius = np.hypot(frequency_x, frequency_y) * sample_scale
    return (original_radius >= _RADIUS_MIN) & (original_radius <= _RADIUS_MAX)


def _windowed_rfft(values: NDArray[np.float64]) -> NDArray[np.complex128]:
    centered = values - float(np.mean(values, dtype=np.float64))
    if not np.any(centered):
        return np.zeros(
            (values.shape[0], values.shape[1] // 2 + 1), dtype=np.complex128
        )
    window_y = np.hanning(values.shape[0])
    window_x = np.hanning(values.shape[1])
    windowed = centered * window_y[:, None] * window_x[None, :]
    return np.fft.rfft2(windowed)


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


def _validate_pixel_ceiling(height: int, width: int) -> None:
    if height * width > _MAX_PAGE_PIXELS:
        raise ValueError("page exceeds the 40-megapixel processing ceiling")


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


def _validate_profile(profile: FingerprintV2Profile) -> None:
    if type(profile) is not FingerprintV2Profile:
        raise TypeError("profile must be a FingerprintV2Profile")
    if profile.schema_version != 2:
        raise ValueError("profile schema_version must be 2")
    candidate_identifier_v2(profile)


def _validate_luminance(luminance: NDArray[np.generic]) -> tuple[int, int]:
    if not isinstance(luminance, np.ndarray):
        raise TypeError("luminance must be a numpy array")
    if luminance.ndim != 2:
        raise ValueError("luminance must be a two-dimensional array")
    height, width = luminance.shape
    if height <= 0 or width <= 0:
        raise ValueError("luminance must be non-empty")
    if not (
        np.issubdtype(luminance.dtype, np.integer)
        or np.issubdtype(luminance.dtype, np.floating)
    ):
        raise TypeError("luminance must use a real numeric dtype")
    return height, width


def _validate_template(template: PilotTemplateV2) -> None:
    if type(template) is not PilotTemplateV2:
        raise TypeError("template must be a PilotTemplateV2")
    height, width = _validate_page_shape(template.page_shape)
    _validate_pixel_ceiling(height, width)
    if (
        not isinstance(template.frequency_pairs, np.ndarray)
        or template.frequency_pairs.dtype != np.float64
        or template.frequency_pairs.shape != (_PILOT_PAIR_COUNT, 2)
        or not template.frequency_pairs.flags.c_contiguous
        or template.frequency_pairs.flags.writeable
        or not np.isfinite(template.frequency_pairs).all()
    ):
        raise ValueError("template frequency_pairs are invalid")
    if (
        not isinstance(template.spatial, np.ndarray)
        or template.spatial.dtype != np.float64
        or template.spatial.shape != (height, width)
        or not template.spatial.flags.c_contiguous
        or template.spatial.flags.writeable
        or not np.isfinite(template.spatial).all()
    ):
        raise ValueError("template spatial pilot is invalid")
