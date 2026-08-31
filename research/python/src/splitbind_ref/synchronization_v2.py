"""Deterministic Fourier pilot synthesis and normalized V2 scoring."""

from __future__ import annotations

import hashlib
import hmac
import math
from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np
from numpy.typing import NDArray

from .fingerprint_v2_profile import FingerprintV2Profile, candidate_identifier_v2
from .synchronization import (
    SyncTemplate,
    _detect,
    _geometry_is_acceptable,
    _to_gray,
    _validate_page,
    validate_sync_template,
)


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
_INTER_AREA_EDGE_EPSILON = 1e-3
_LOG_POLAR_SIZE = (512, 720)
_LOG_POLAR_SPECTRUM_SIDE = 512
_LOG_POLAR_RADIUS_MIN = 0.04
_LOG_POLAR_RADIUS_MAX = 0.30
_LOG_POLAR_PEAK_LIMIT = 32
_LOG_POLAR_NMS_RADIUS_PX = 2
_PILOT_FREQUENCY_RADIUS = 0.02
_FREQUENCY_PEAK_RADIUS_PX = 5
_SCALE_MIN = 0.45
_SCALE_MAX = 1.60
_ROTATION_MIN_DEGREES = -8.0
_ROTATION_MAX_DEGREES = 8.0
_TRANSLATION_FRACTION_MAX = 0.60
_MAX_PILOT_HYPOTHESES = 3
_MAX_HOMOGRAPHY_CONDITION = 100.0
_MAX_SIMILARITY_REPROJECTION_RMSE_PX = 3.0
_MIN_CORNER_COVERAGE = 0.20
_MAX_CORNER_AREA_RATIO = 5.0
_CORNER_MARGIN_FRACTION = 0.65
_PURE_RESIZE_SCALE_TOLERANCE = 5e-4
_PURE_RESIZE_SHEAR_TOLERANCE = 1e-4
_PURE_RESIZE_TRANSLATION_TOLERANCE_PX = 0.5
_PURE_RESIZE_PERSPECTIVE_TOLERANCE = 1e-12


class AlignmentV2RuntimeError(RuntimeError):
    """Typed boundary for runtime failures that are not evidence rejection."""

    def __init__(
        self,
        stage: Literal[
            "pilot_estimation",
            "orb_estimation",
            "geometry_validation",
            "canonical_warp",
        ],
        hypothesis_count: int,
    ) -> None:
        self.stage = stage
        self.hypothesis_count = hypothesis_count
        super().__init__(
            f"V2 alignment runtime failure during {stage} "
            f"after {hypothesis_count} hypotheses"
        )


@dataclass(frozen=True, slots=True)
class GeometryHypothesisV2:
    homography: NDArray[np.float64]
    pilot_score: float
    source: Literal["pilot", "orb"]


@dataclass(frozen=True, slots=True)
class AlignmentV2Result:
    image: NDArray[np.uint8] | None
    homography: NDArray[np.float64] | None
    pilot_score: float
    hypothesis_count: int
    reason: Literal[
        "aligned", "insufficient_sync_evidence", "geometry_rejected"
    ]


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


@dataclass(frozen=True, slots=True)
class _PilotGeometryTemplateV2:
    """Direct bounded rendering of a canonical pilot for geometry only."""

    page_shape: tuple[int, int]
    frequency_pairs: NDArray[np.float64]
    spatial: NDArray[np.float64]
    sample_scale: float


def align_page_v2(
    page_bgr: NDArray[np.uint8],
    key: bytes,
    page_index: int,
    profile: FingerprintV2Profile,
    canonical_shape: tuple[int, int],
    orb_template: SyncTemplate | None = None,
) -> AlignmentV2Result:
    """Map one attacked page to the canonical V2 canvas using bounded evidence."""

    page = _validate_page(page_bgr)
    canonical_height, canonical_width = _validate_page_shape(canonical_shape)
    _validate_pixel_ceiling(canonical_height, canonical_width)
    _validate_key(key)
    _validate_page_index(page_index)
    _validate_profile(profile)
    validated_orb = None
    if orb_template is not None:
        validated_orb = validate_sync_template(orb_template)
        if validated_orb.page_shape != (canonical_height, canonical_width):
            raise ValueError("orb_template page_shape must match canonical_shape")

    try:
        sample_scale = _geometry_sample_scale(
            page.shape[:2], (canonical_height, canonical_width)
        )
        pilot_page = _bounded_geometry_page(page, sample_scale)
        template = _synthesize_geometry_pilot_v2(
            (canonical_height, canonical_width),
            sample_scale,
            key,
            page_index,
            profile,
        )
        pilot_hypotheses = list(
            _pilot_hypotheses_v2(_to_gray(pilot_page), template, profile)
        )[:_MAX_PILOT_HYPOTHESES]
    except cv2.error as error:
        raise AlignmentV2RuntimeError("pilot_estimation", 0) from error
    try:
        orb_hypothesis = (
            _orb_hypothesis_v2(page, validated_orb)
            if validated_orb is not None
            else None
        )
    except cv2.error as error:
        raise AlignmentV2RuntimeError(
            "orb_estimation", len(pilot_hypotheses)
        ) from error

    hypotheses = pilot_hypotheses.copy()
    if orb_hypothesis is not None:
        hypotheses.append(orb_hypothesis)
    hypothesis_count = len(hypotheses)

    eligible = [
        hypothesis
        for hypothesis in hypotheses
        if hypothesis.source == "orb"
        or (
            math.isfinite(float(hypothesis.pilot_score))
            and float(hypothesis.pilot_score) >= profile.pilot_score_min
        )
    ]
    if not eligible:
        best_score = max(
            (
                float(hypothesis.pilot_score)
                for hypothesis in pilot_hypotheses
                if math.isfinite(float(hypothesis.pilot_score))
            ),
            default=0.0,
        )
        return AlignmentV2Result(
            None,
            None,
            float(np.clip(best_score, -1.0, 1.0)),
            hypothesis_count,
            "insufficient_sync_evidence",
        )

    try:
        safe = [
            hypothesis
            for hypothesis in eligible
            if _geometry_is_acceptable_v2(
                hypothesis.homography,
                page.shape[:2],
                (canonical_height, canonical_width),
            )
        ]
    except cv2.error as error:
        raise AlignmentV2RuntimeError(
            "geometry_validation", hypothesis_count
        ) from error
    if not safe:
        return AlignmentV2Result(None, None, 0.0, hypothesis_count, "geometry_rejected")

    winner = max(
        safe,
        key=lambda hypothesis: (
            float(hypothesis.pilot_score), hypothesis.source == "pilot"
        ),
    )
    matrix = np.asarray(winner.homography, dtype=np.float64)
    divisor = float(matrix[2, 2])
    if not math.isfinite(divisor) or abs(divisor) <= 1e-12:
        return AlignmentV2Result(None, None, 0.0, hypothesis_count, "geometry_rejected")
    matrix = matrix / divisor
    if winner.source == "pilot":
        matrix = _snap_pure_resize_homography(
            matrix, page.shape[:2], (canonical_height, canonical_width)
        )
    try:
        aligned = cv2.warpPerspective(
            page,
            matrix,
            (canonical_width, canonical_height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT_101,
        )
    except cv2.error as error:
        raise AlignmentV2RuntimeError(
            "canonical_warp", hypothesis_count
        ) from error
    return AlignmentV2Result(
        image=np.ascontiguousarray(aligned, dtype=np.uint8),
        homography=np.ascontiguousarray(matrix, dtype=np.float64),
        pilot_score=float(np.clip(winner.pilot_score, -1.0, 1.0)),
        hypothesis_count=hypothesis_count,
        reason="aligned",
    )


def _snap_pure_resize_homography(
    homography: NDArray[np.float64],
    source_shape: tuple[int, int],
    canonical_shape: tuple[int, int],
) -> NDArray[np.float64]:
    """Use the exact OpenCV pixel-center inverse for a pilot-confirmed resize."""

    source_height, source_width = source_shape
    canonical_height, canonical_width = canonical_shape
    scale_x = canonical_width / source_width
    scale_y = canonical_height / source_height
    if (
        source_shape == canonical_shape
        or not math.isclose(scale_x, scale_y, rel_tol=1e-12, abs_tol=0.0)
    ):
        return homography

    expected = np.array(
        [
            [scale_x, 0.0, (scale_x - 1.0) / 2.0],
            [0.0, scale_y, (scale_y - 1.0) / 2.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    if (
        abs(float(homography[0, 0]) - scale_x) > _PURE_RESIZE_SCALE_TOLERANCE
        or abs(float(homography[1, 1]) - scale_y) > _PURE_RESIZE_SCALE_TOLERANCE
        or abs(float(homography[0, 1])) > _PURE_RESIZE_SHEAR_TOLERANCE
        or abs(float(homography[1, 0])) > _PURE_RESIZE_SHEAR_TOLERANCE
        or abs(float(homography[2, 0])) > _PURE_RESIZE_PERSPECTIVE_TOLERANCE
        or abs(float(homography[2, 1])) > _PURE_RESIZE_PERSPECTIVE_TOLERANCE
        or abs(float(homography[0, 2]) - expected[0, 2])
        > _PURE_RESIZE_TRANSLATION_TOLERANCE_PX
        or abs(float(homography[1, 2]) - expected[1, 2])
        > _PURE_RESIZE_TRANSLATION_TOLERANCE_PX
    ):
        return homography
    return expected


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

    frequencies, phases, amplitudes = _derive_pilot_components(
        key, page_index, profile
    )
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


def _derive_pilot_components(
    key: bytes, page_index: int, profile: FingerprintV2Profile
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    domain = _SEED_DOMAIN + page_index.to_bytes(4, "big")
    seed = hmac.new(
        key, domain + candidate_identifier_v2(profile), hashlib.sha256
    ).digest()
    return _derive_constellation(_HmacByteStream(seed))


def _geometry_sample_scale(
    source_shape: tuple[int, int], canonical_shape: tuple[int, int]
) -> float:
    long_edge = max(*source_shape, *canonical_shape)
    return min(1.0, _FFT_LONG_EDGE_MAX / long_edge)


def _scaled_geometry_shape(
    shape: tuple[int, int], sample_scale: float
) -> tuple[int, int]:
    height, width = shape
    return (
        max(1, int(round(height * sample_scale))),
        max(1, int(round(width * sample_scale))),
    )


def _bounded_geometry_page(
    page: NDArray[np.uint8], sample_scale: float
) -> NDArray[np.uint8]:
    if sample_scale == 1.0:
        return page
    height, width = _scaled_geometry_shape(page.shape[:2], sample_scale)
    return np.ascontiguousarray(
        cv2.resize(page, (width, height), interpolation=cv2.INTER_AREA),
        dtype=np.uint8,
    )


def _synthesize_geometry_pilot_v2(
    canonical_shape: tuple[int, int],
    sample_scale: float,
    key: bytes,
    page_index: int,
    profile: FingerprintV2Profile,
) -> _PilotGeometryTemplateV2:
    canonical_height, canonical_width = canonical_shape
    working_height, working_width = _scaled_geometry_shape(
        canonical_shape, sample_scale
    )
    frequencies, phases, amplitudes = _derive_pilot_components(
        key, page_index, profile
    )
    if sample_scale == 1.0:
        sampled_frequencies = frequencies
        spatial = _synthesize_spatial(
            working_height,
            working_width,
            frequencies,
            phases,
            amplitudes,
        )
    else:
        scale_x = working_width / canonical_width
        scale_y = working_height / canonical_height
        unwrapped_frequencies = frequencies / np.asarray(
            (scale_x, scale_y), dtype=np.float64
        )
        sampled_frequencies = (unwrapped_frequencies + 0.5) % 1.0 - 0.5
        spatial = _synthesize_spatial(
            working_height,
            working_width,
            frequencies,
            phases,
            amplitudes,
            source_shape=canonical_shape,
        )
    return _PilotGeometryTemplateV2(
        page_shape=canonical_shape,
        frequency_pairs=np.ascontiguousarray(
            sampled_frequencies, dtype=np.float64
        ),
        spatial=np.ascontiguousarray(spatial, dtype=np.float64),
        sample_scale=sample_scale,
    )


def _working_frequency_pairs(
    template: PilotTemplateV2 | _PilotGeometryTemplateV2,
    sample_scale: float,
) -> NDArray[np.float64]:
    if isinstance(template, _PilotGeometryTemplateV2):
        return template.frequency_pairs
    return template.frequency_pairs / sample_scale


def _pilot_hypotheses_v2(
    luminance: NDArray[np.uint8],
    template: PilotTemplateV2 | _PilotGeometryTemplateV2,
    profile: FingerprintV2Profile,
) -> tuple[GeometryHypothesisV2, ...]:
    """Estimate bounded similarity candidates from log-polar pilot evidence."""

    if isinstance(template, _PilotGeometryTemplateV2):
        geometry_views = (
            np.ascontiguousarray(luminance, dtype=np.float64),
            template.spatial,
            template.sample_scale,
        )
    else:
        geometry_views = _bounded_geometry_views(luminance, template.spatial)
    signal_view, template_view, _ = geometry_views
    log_template, log_radius_scale = _log_polar_magnitude(template_view)
    log_signal, _ = _log_polar_magnitude(signal_view)
    candidates = _log_polar_similarity_candidates(
        log_template, log_signal, log_radius_scale
    )

    refined_candidates: list[tuple[float, float, float]] = []
    for initial_scale, initial_rotation, response in candidates:
        refined_scale, refined_rotation = _refine_similarity_from_pilot_peaks(
            luminance,
            template,
            initial_scale,
            initial_rotation,
            geometry_views=geometry_views,
        )
        if not (
            _SCALE_MIN <= refined_scale <= _SCALE_MAX
            and _ROTATION_MIN_DEGREES
            <= refined_rotation
            <= _ROTATION_MAX_DEGREES
        ):
            continue
        refined_candidates.append((refined_scale, refined_rotation, response))

    hypotheses: list[GeometryHypothesisV2] = []
    for refined_scale, refined_rotation, _ in _nms_similarity_candidates(
        refined_candidates
    ):
        hypotheses.extend(
            _translation_and_score_hypotheses(
                luminance,
                template,
                refined_scale,
                refined_rotation,
                geometry_views=geometry_views,
            )
        )
    return _nms_pilot_hypotheses(hypotheses, template.page_shape)


def _log_polar_similarity_candidates(
    log_template: NDArray[np.float32],
    log_signal: NDArray[np.float32],
    log_radius_scale: float,
) -> tuple[tuple[float, float, float], ...]:
    reference_fft = np.fft.fft2(log_template.astype(np.float64, copy=False))
    signal_fft = np.fft.fft2(log_signal.astype(np.float64, copy=False))
    cross_power = signal_fft * np.conj(reference_fft)
    magnitude = np.abs(cross_power)
    usable = np.isfinite(magnitude) & (magnitude > 1e-12)
    if not np.any(usable):
        return ()
    normalized = np.zeros_like(cross_power)
    normalized[usable] = cross_power[usable] / magnitude[usable]
    surface = np.fft.ifft2(normalized).real
    if not np.isfinite(surface).all():
        return ()

    candidates: list[tuple[float, float, float]] = []
    height, width = surface.shape
    for peak_x, peak_y, response in _cyclic_nms_peaks(
        surface,
        maximum=_LOG_POLAR_PEAK_LIMIT,
        radius_x=_LOG_POLAR_NMS_RADIUS_PX,
        radius_y=_LOG_POLAR_NMS_RADIUS_PX,
    ):
        shift_x = _signed_cyclic_coordinate(
            peak_x + _cyclic_quadratic_offset(surface[peak_y], peak_x), width
        )
        shift_y = _signed_cyclic_coordinate(
            peak_y + _cyclic_quadratic_offset(surface[:, peak_x], peak_y), height
        )
        scale = math.exp(-shift_x / log_radius_scale)
        rotation = _wrap_degrees(-shift_y * 360.0 / height)
        candidates.append((scale, rotation, response))
    return _nms_similarity_candidates(candidates)


def _cyclic_nms_peaks(
    surface: NDArray[np.float64],
    *,
    maximum: int,
    radius_x: int,
    radius_y: int,
) -> tuple[tuple[int, int, float], ...]:
    """Select separated maxima while treating opposite FFT edges as adjacent."""

    if surface.ndim != 2 or maximum <= 0:
        return ()
    working = np.asarray(surface, dtype=np.float64).copy()
    working[~np.isfinite(working)] = -math.inf
    height, width = working.shape
    x_coordinates = np.arange(width)
    y_coordinates = np.arange(height)
    peaks: list[tuple[int, int, float]] = []
    for _ in range(maximum):
        flat_index = int(np.argmax(working))
        response = float(working.flat[flat_index])
        if not math.isfinite(response):
            break
        peak_y, peak_x = np.unravel_index(flat_index, working.shape)
        peaks.append((int(peak_x), int(peak_y), response))
        x_distance = np.abs(x_coordinates - peak_x)
        y_distance = np.abs(y_coordinates - peak_y)
        x_near = np.minimum(x_distance, width - x_distance) <= radius_x
        y_near = np.minimum(y_distance, height - y_distance) <= radius_y
        working[np.ix_(y_near, x_near)] = -math.inf
    return tuple(peaks)


def _log_polar_magnitude(
    values: NDArray[np.generic],
) -> tuple[NDArray[np.float32], float]:
    bounded = _bounded_fft_view(values)
    centered = bounded - float(np.mean(bounded, dtype=np.float64))
    window = np.outer(np.hanning(centered.shape[0]), np.hanning(centered.shape[1]))
    spectrum = np.log1p(
        np.abs(np.fft.fftshift(np.fft.fft2(centered * window)))
    ).astype(np.float32)
    normalized = cv2.resize(
        spectrum,
        (_LOG_POLAR_SPECTRUM_SIDE, _LOG_POLAR_SPECTRUM_SIDE),
        interpolation=cv2.INTER_LINEAR,
    )
    center = (_LOG_POLAR_SPECTRUM_SIDE - 1.0) / 2.0
    y, x = np.indices(normalized.shape, dtype=np.float64)
    radius = np.hypot(x - center, y - center) / _LOG_POLAR_SPECTRUM_SIDE
    normalized[
        (radius < _LOG_POLAR_RADIUS_MIN) | (radius > _LOG_POLAR_RADIUS_MAX)
    ] = 0.0
    maximum_radius = center
    log_polar = cv2.warpPolar(
        normalized,
        _LOG_POLAR_SIZE,
        (center, center),
        maximum_radius,
        cv2.WARP_POLAR_LOG | cv2.INTER_LINEAR | cv2.WARP_FILL_OUTLIERS,
    )
    log_radius_scale = _LOG_POLAR_SIZE[0] / math.log(maximum_radius)
    return np.ascontiguousarray(log_polar, dtype=np.float32), log_radius_scale


def _bounded_fft_view(values: NDArray[np.generic]) -> NDArray[np.float64]:
    height, width = values.shape
    long_edge = max(height, width)
    if long_edge <= _FFT_LONG_EDGE_MAX:
        return np.ascontiguousarray(values, dtype=np.float64)
    ratio = _FFT_LONG_EDGE_MAX / long_edge
    resized = cv2.resize(
        values.astype(np.float64, copy=False),
        (max(1, round(width * ratio)), max(1, round(height * ratio))),
        interpolation=cv2.INTER_AREA,
    )
    return np.ascontiguousarray(resized, dtype=np.float64)


def _nms_similarity_candidates(
    candidates: list[tuple[float, float, float]],
) -> tuple[tuple[float, float, float], ...]:
    accepted: list[tuple[float, float, float]] = []
    for scale, rotation, response in sorted(
        candidates, key=lambda candidate: candidate[2], reverse=True
    ):
        if not all(math.isfinite(value) for value in (scale, rotation, response)):
            continue
        if not (
            _SCALE_MIN <= scale <= _SCALE_MAX
            and _ROTATION_MIN_DEGREES <= rotation <= _ROTATION_MAX_DEGREES
        ):
            continue
        if any(
            abs(math.log(scale / previous_scale)) < 0.01
            and abs(rotation - previous_rotation) < 0.25
            for previous_scale, previous_rotation, _ in accepted
        ):
            continue
        accepted.append((scale, rotation, response))
        if len(accepted) == _MAX_PILOT_HYPOTHESES:
            break
    return tuple(accepted)


def _refine_similarity_from_pilot_peaks(
    luminance: NDArray[np.uint8],
    template: PilotTemplateV2 | _PilotGeometryTemplateV2,
    initial_scale: float,
    initial_rotation: float,
    *,
    geometry_views: tuple[
        NDArray[np.float64], NDArray[np.float64], float
    ]
    | None = None,
) -> tuple[float, float]:
    if geometry_views is None:
        geometry_views = _bounded_geometry_views(luminance, template.spatial)
    signal_view, _, sample_scale = geometry_views
    height, width = signal_view.shape
    centered = signal_view - float(np.mean(signal_view))
    centered *= np.outer(np.hanning(height), np.hanning(width))
    magnitude = np.abs(np.fft.fftshift(np.fft.fft2(centered)))
    forward_linear = _similarity_linear(initial_scale, initial_rotation)
    frequency_linear = np.linalg.inv(forward_linear).T
    expected: list[NDArray[np.float64]] = []
    observed: list[NDArray[np.float64]] = []
    sampled_frequencies = _working_frequency_pairs(template, sample_scale)
    for frequency in sampled_frequencies:
        predicted = frequency_linear @ frequency
        peak = _local_frequency_peak(magnitude, predicted)
        if peak is not None:
            expected.append(frequency)
            observed.append(peak)
    if len(expected) < 6:
        return initial_scale, initial_rotation

    cv2.setRNGSeed(0)
    fitted, inliers = cv2.estimateAffinePartial2D(
        np.asarray(expected, dtype=np.float64),
        np.asarray(observed, dtype=np.float64),
        method=cv2.RANSAC,
        ransacReprojThreshold=0.002,
        maxIters=2000,
        confidence=0.999,
        refineIters=10,
    )
    if fitted is None or inliers is None or int(np.count_nonzero(inliers)) < 6:
        return initial_scale, initial_rotation
    fitted_frequency = np.asarray(fitted[:, :2], dtype=np.float64)
    if not np.isfinite(fitted_frequency).all():
        return initial_scale, initial_rotation
    try:
        fitted_forward = np.linalg.inv(fitted_frequency.T)
    except np.linalg.LinAlgError:
        return initial_scale, initial_rotation
    determinant = float(np.linalg.det(fitted_forward))
    if not math.isfinite(determinant) or determinant <= 0.0:
        return initial_scale, initial_rotation
    scale = math.sqrt(determinant)
    rotation = _wrap_degrees(
        math.degrees(math.atan2(fitted_forward[0, 1], fitted_forward[0, 0]))
    )
    return scale, rotation


def _local_frequency_peak(
    magnitude: NDArray[np.float64], frequency: NDArray[np.float64]
) -> NDArray[np.float64] | None:
    height, width = magnitude.shape
    center_x = width // 2
    center_y = height // 2
    predicted_x = int(round(float(frequency[0]) * width + center_x))
    predicted_y = int(round(float(frequency[1]) * height + center_y))
    radius = _FREQUENCY_PEAK_RADIUS_PX
    if not (
        radius <= predicted_x < width - radius
        and radius <= predicted_y < height - radius
    ):
        return None
    patch = magnitude[
        predicted_y - radius : predicted_y + radius + 1,
        predicted_x - radius : predicted_x + radius + 1,
    ]
    offset_y, offset_x = np.unravel_index(int(np.argmax(patch)), patch.shape)
    peak_x = predicted_x - radius + int(offset_x)
    peak_y = predicted_y - radius + int(offset_y)
    subpixel_x = _quadratic_peak_offset(magnitude[peak_y, peak_x - 1 : peak_x + 2])
    subpixel_y = _quadratic_peak_offset(magnitude[peak_y - 1 : peak_y + 2, peak_x])
    return np.asarray(
        (
            (peak_x + subpixel_x - center_x) / width,
            (peak_y + subpixel_y - center_y) / height,
        ),
        dtype=np.float64,
    )


def _quadratic_peak_offset(samples: NDArray[np.float64]) -> float:
    left, center, right = np.log1p(samples.astype(np.float64))
    divisor = float(left - 2.0 * center + right)
    if not math.isfinite(divisor) or abs(divisor) <= 1e-12:
        return 0.0
    offset = 0.5 * float(left - right) / divisor
    return float(np.clip(offset, -1.0, 1.0))


def _translation_and_score_hypotheses(
    luminance: NDArray[np.uint8],
    template: PilotTemplateV2 | _PilotGeometryTemplateV2,
    scale: float,
    rotation: float,
    *,
    geometry_views: tuple[
        NDArray[np.float64], NDArray[np.float64], float
    ]
    | None = None,
) -> tuple[GeometryHypothesisV2, ...]:
    if geometry_views is None:
        geometry_views = _bounded_geometry_views(luminance, template.spatial)
    signal_view, template_view, sample_scale = geometry_views
    height, width = signal_view.shape
    forward_linear = _similarity_linear(scale, rotation)
    affine = np.column_stack((forward_linear, np.zeros(2, dtype=np.float64)))
    predicted = cv2.warpAffine(
        template_view,
        affine,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0.0,
    )
    predicted_fft = np.fft.fft2(predicted)
    centered = signal_view - float(np.mean(signal_view))
    signal_fft = np.fft.fft2(centered)
    frequency_linear = np.linalg.inv(forward_linear).T
    mask = _transformed_pilot_mask(
        (height, width),
        _working_frequency_pairs(template, sample_scale),
        frequency_linear,
        radius=_PILOT_FREQUENCY_RADIUS / sample_scale,
    )
    predicted_energy = float(np.sum(np.abs(predicted_fft[mask]) ** 2))
    signal_energy = float(np.sum(np.abs(signal_fft[mask]) ** 2))
    if predicted_energy <= 0.0 or signal_energy <= 0.0:
        return ()
    cross_spectrum = np.zeros((height, width), dtype=np.complex128)
    cross_spectrum[mask] = signal_fft[mask] * np.conj(predicted_fft[mask])
    correlation = np.fft.ifft2(cross_spectrum).real
    peak_y, peak_x = np.unravel_index(int(np.argmax(correlation)), correlation.shape)
    base_translation_x = _signed_cyclic_coordinate(
        peak_x + _cyclic_quadratic_offset(correlation[peak_y], peak_x), width
    )
    base_translation_y = _signed_cyclic_coordinate(
        peak_y + _cyclic_quadratic_offset(correlation[:, peak_x], peak_y), height
    )
    translation_bound_x = (
        _TRANSLATION_FRACTION_MAX * template.page_shape[1] * sample_scale
    )
    translation_bound_y = (
        _TRANSLATION_FRACTION_MAX * template.page_shape[0] * sample_scale
    )
    aliases_x = _bounded_translation_aliases(
        base_translation_x, width, translation_bound_x
    )
    aliases_y = _bounded_translation_aliases(
        base_translation_y, height, translation_bound_y
    )

    signal_band = np.fft.ifft2(signal_fft * mask).real
    predicted_band = np.fft.ifft2(predicted_fft * mask).real
    denominator = math.sqrt(
        float(np.sum(signal_band * signal_band))
        * float(np.sum(predicted_band * predicted_band))
    )
    if not math.isfinite(denominator) or denominator <= 0.0:
        return ()

    hypotheses: list[GeometryHypothesisV2] = []
    for sampled_translation_x in aliases_x:
        for sampled_translation_y in aliases_y:
            slices = _noncyclic_overlap_slices(
                sampled_translation_x,
                sampled_translation_y,
                width,
                height,
            )
            if slices is None:
                continue
            signal_y, signal_x, predicted_y, predicted_x = slices
            numerator = float(
                np.sum(
                    signal_band[signal_y, signal_x]
                    * predicted_band[predicted_y, predicted_x]
                )
            )
            score = numerator / denominator
            if not math.isfinite(score):
                continue
            translation_x = sampled_translation_x / sample_scale
            translation_y = sampled_translation_y / sample_scale
            forward = np.array(
                [
                    [
                        forward_linear[0, 0],
                        forward_linear[0, 1],
                        translation_x,
                    ],
                    [
                        forward_linear[1, 0],
                        forward_linear[1, 1],
                        translation_y,
                    ],
                    [0.0, 0.0, 1.0],
                ],
                dtype=np.float64,
            )
            try:
                homography = np.linalg.inv(forward)
            except np.linalg.LinAlgError:
                continue
            hypotheses.append(
                GeometryHypothesisV2(
                    np.ascontiguousarray(homography, dtype=np.float64),
                    float(np.clip(score, -1.0, 1.0)),
                    "pilot",
                )
            )
    return tuple(hypotheses)


def _translation_and_score_hypothesis(
    luminance: NDArray[np.uint8],
    template: PilotTemplateV2 | _PilotGeometryTemplateV2,
    scale: float,
    rotation: float,
    *,
    geometry_views: tuple[
        NDArray[np.float64], NDArray[np.float64], float
    ]
    | None = None,
) -> GeometryHypothesisV2 | None:
    """Compatibility wrapper returning the strongest bounded translation alias."""

    hypotheses = _translation_and_score_hypotheses(
        luminance,
        template,
        scale,
        rotation,
        geometry_views=geometry_views,
    )
    return max(hypotheses, key=lambda item: item.pilot_score, default=None)


def _bounded_translation_aliases(
    base: float, period: int, bound: float
) -> tuple[float, ...]:
    if not all(math.isfinite(value) for value in (base, bound)) or period <= 0:
        return ()
    overlap_bound = min(bound, math.nextafter(float(period), 0.0))
    first = math.ceil((-overlap_bound - base) / period)
    last = math.floor((overlap_bound - base) / period)
    return tuple(base + offset * period for offset in range(first, last + 1))


def _noncyclic_overlap_slices(
    translation_x: float,
    translation_y: float,
    width: int,
    height: int,
) -> tuple[slice, slice, slice, slice] | None:
    offset_x = int(round(translation_x))
    offset_y = int(round(translation_y))
    if abs(offset_x) >= width or abs(offset_y) >= height:
        return None
    if offset_x >= 0:
        signal_x = slice(offset_x, width)
        predicted_x = slice(0, width - offset_x)
    else:
        signal_x = slice(0, width + offset_x)
        predicted_x = slice(-offset_x, width)
    if offset_y >= 0:
        signal_y = slice(offset_y, height)
        predicted_y = slice(0, height - offset_y)
    else:
        signal_y = slice(0, height + offset_y)
        predicted_y = slice(-offset_y, height)
    return signal_y, signal_x, predicted_y, predicted_x


def _nms_pilot_hypotheses(
    hypotheses: list[GeometryHypothesisV2], canonical_shape: tuple[int, int]
) -> tuple[GeometryHypothesisV2, ...]:
    height, width = canonical_shape
    corners = np.asarray(
        (
            ((0.0, 0.0),),
            ((width - 1.0, 0.0),),
            ((width - 1.0, height - 1.0),),
            ((0.0, height - 1.0),),
        ),
        dtype=np.float64,
    )
    accepted: list[GeometryHypothesisV2] = []
    accepted_corners: list[NDArray[np.float64]] = []
    for hypothesis in sorted(
        hypotheses, key=lambda item: item.pilot_score, reverse=True
    ):
        try:
            forward = np.linalg.inv(hypothesis.homography)
        except np.linalg.LinAlgError:
            continue
        projected = cv2.perspectiveTransform(corners, forward)
        if any(
            float(np.sqrt(np.mean(np.sum((projected - previous) ** 2, axis=2))))
            <= _MAX_SIMILARITY_REPROJECTION_RMSE_PX
            for previous in accepted_corners
        ):
            continue
        accepted.append(hypothesis)
        accepted_corners.append(projected)
        if len(accepted) == _MAX_PILOT_HYPOTHESES:
            break
    return tuple(accepted)


def _bounded_geometry_views(
    luminance: NDArray[np.generic], spatial: NDArray[np.float64]
) -> tuple[NDArray[np.float64], NDArray[np.float64], float]:
    """Resize attacked and canonical inputs by one factor to preserve geometry."""

    signal_height, signal_width = luminance.shape
    template_height, template_width = spatial.shape
    long_edge = max(
        signal_height, signal_width, template_height, template_width
    )
    sample_scale = min(1.0, _FFT_LONG_EDGE_MAX / long_edge)
    if sample_scale == 1.0:
        return (
            np.ascontiguousarray(luminance, dtype=np.float64),
            np.ascontiguousarray(spatial, dtype=np.float64),
            sample_scale,
        )
    signal_size = (
        max(1, int(round(signal_width * sample_scale))),
        max(1, int(round(signal_height * sample_scale))),
    )
    template_size = (
        max(1, int(round(template_width * sample_scale))),
        max(1, int(round(template_height * sample_scale))),
    )
    signal_view = cv2.resize(
        luminance, signal_size, interpolation=cv2.INTER_AREA
    )
    template_view = cv2.resize(
        spatial, template_size, interpolation=cv2.INTER_AREA
    )
    return (
        np.ascontiguousarray(signal_view, dtype=np.float64),
        np.ascontiguousarray(template_view, dtype=np.float64),
        sample_scale,
    )


def _transformed_pilot_mask(
    shape: tuple[int, int],
    frequencies: NDArray[np.float64],
    frequency_linear: NDArray[np.float64],
    *,
    radius: float,
) -> NDArray[np.bool_]:
    height, width = shape
    frequency_y = np.fft.fftfreq(height)[:, None]
    frequency_x = np.fft.fftfreq(width)[None, :]
    mask = np.zeros((height, width), dtype=np.bool_)
    for frequency in frequencies:
        transformed = frequency_linear @ frequency
        for sign in (-1.0, 1.0):
            mask |= (
                (frequency_x - sign * transformed[0]) ** 2
                + (frequency_y - sign * transformed[1]) ** 2
                <= radius**2
            )
    return mask


def _cyclic_quadratic_offset(values: NDArray[np.float64], index: int) -> float:
    samples = np.asarray(
        (
            values[(index - 1) % len(values)],
            values[index],
            values[(index + 1) % len(values)],
        ),
        dtype=np.float64,
    )
    divisor = float(samples[0] - 2.0 * samples[1] + samples[2])
    if not math.isfinite(divisor) or abs(divisor) <= 1e-12:
        return 0.0
    return float(np.clip(0.5 * (samples[0] - samples[2]) / divisor, -1.0, 1.0))


def _signed_cyclic_coordinate(value: float, period: int) -> float:
    return value - period if value > period / 2.0 else value


def _similarity_linear(scale: float, degrees: float) -> NDArray[np.float64]:
    radians = math.radians(degrees)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    return scale * np.asarray(((cosine, sine), (-sine, cosine)), dtype=np.float64)


def _wrap_degrees(value: float) -> float:
    return (value + 180.0) % 360.0 - 180.0


def _orb_hypothesis_v2(
    page_bgr: NDArray[np.uint8], template: SyncTemplate
) -> GeometryHypothesisV2 | None:
    keypoints, descriptors = _detect(_to_gray(page_bgr))
    if descriptors is None or len(keypoints) < 4:
        return None
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    pairs = matcher.knnMatch(descriptors, template.descriptors, k=2)
    matches = [
        first
        for pair in pairs
        if len(pair) == 2
        for first, second in [pair]
        if first.distance < 0.75 * second.distance
    ]
    if len(matches) < 8:
        return None
    source = np.asarray(
        [keypoints[match.queryIdx].pt for match in matches], dtype=np.float64
    ).reshape(-1, 1, 2)
    target = np.asarray(
        [template.keypoints[match.trainIdx] for match in matches], dtype=np.float64
    ).reshape(-1, 1, 2)
    cv2.setRNGSeed(0)
    matrix, inlier_mask = cv2.findHomography(
        source,
        target,
        method=cv2.RANSAC,
        ransacReprojThreshold=3.0,
        maxIters=2000,
        confidence=0.995,
    )
    if matrix is None or inlier_mask is None:
        return None
    if not _orb_geometry_is_acceptable_v2(
        matrix,
        source,
        target,
        inlier_mask,
        page_bgr.shape[:2],
        template.page_shape,
    ):
        return None
    if not _geometry_is_acceptable_v2(
        matrix, page_bgr.shape[:2], template.page_shape
    ):
        return None
    normalized = np.asarray(matrix, dtype=np.float64)
    divisor = float(normalized[2, 2])
    if not math.isfinite(divisor) or abs(divisor) <= 1e-12:
        return None
    return GeometryHypothesisV2(
        np.ascontiguousarray(normalized / divisor, dtype=np.float64), 0.0, "orb"
    )


def _orb_geometry_is_acceptable_v2(
    homography: object,
    source: NDArray[np.float64],
    target: NDArray[np.float64],
    inlier_mask: object,
    source_shape: tuple[int, int],
    target_shape: tuple[int, int],
) -> bool:
    return _geometry_is_acceptable(
        homography,
        source,
        target,
        inlier_mask,
        source_shape,
        target_shape,
    )


def _geometry_is_acceptable_v2(
    homography: object,
    source_shape: tuple[int, int],
    target_shape: tuple[int, int],
) -> bool:
    """Reject unsafe V2 geometry before allocating a canonical page raster."""

    matrix = np.asarray(homography)
    if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
        return False
    divisor = float(matrix[2, 2])
    if not math.isfinite(divisor) or abs(divisor) <= 1e-12:
        return False
    matrix = matrix.astype(np.float64) / divisor
    source_height, source_width = source_shape
    target_height, target_width = target_shape
    source_scale = np.diag(
        (max(1.0, source_width - 1.0), max(1.0, source_height - 1.0), 1.0)
    )
    target_scale = np.diag(
        (
            1.0 / max(1.0, target_width - 1.0),
            1.0 / max(1.0, target_height - 1.0),
            1.0,
        )
    )
    condition = float(np.linalg.cond(target_scale @ matrix @ source_scale))
    if not math.isfinite(condition) or condition > _MAX_HOMOGRAPHY_CONDITION:
        return False
    try:
        forward = np.linalg.inv(matrix)
    except np.linalg.LinAlgError:
        return False
    if not np.all(np.isfinite(forward)) or abs(float(forward[2, 2])) <= 1e-12:
        return False
    forward /= float(forward[2, 2])
    determinant = float(np.linalg.det(matrix))
    if not math.isfinite(determinant) or determinant <= 0.0:
        return False

    target_grid = np.asarray(
        [
            [[x, y]]
            for y in (0.0, (target_height - 1.0) / 2.0, target_height - 1.0)
            for x in (0.0, (target_width - 1.0) / 2.0, target_width - 1.0)
        ],
        dtype=np.float64,
    )
    projected_grid = cv2.perspectiveTransform(target_grid, forward).reshape(-1, 2)
    if not np.all(np.isfinite(projected_grid)):
        return False
    similarity, reprojection_rmse = _fit_similarity_v2(
        target_grid.reshape(-1, 2), projected_grid
    )
    if (
        similarity is None
        or reprojection_rmse > _MAX_SIMILARITY_REPROJECTION_RMSE_PX
    ):
        return False
    linear = similarity[:2, :2]
    scale = math.sqrt(float(np.linalg.det(linear)))
    rotation = _wrap_degrees(
        math.degrees(math.atan2(linear[0, 1], linear[0, 0]))
    )
    if not _SCALE_MIN <= scale <= _SCALE_MAX:
        return False
    if not _ROTATION_MIN_DEGREES <= rotation <= _ROTATION_MAX_DEGREES:
        return False

    translation_x = float(similarity[0, 2])
    translation_y = float(similarity[1, 2])
    if abs(translation_x) > _TRANSLATION_FRACTION_MAX * target_width:
        return False
    if abs(translation_y) > _TRANSLATION_FRACTION_MAX * target_height:
        return False

    source_corners = np.asarray(
        [
            [[0.0, 0.0]],
            [[source_width - 1.0, 0.0]],
            [[source_width - 1.0, source_height - 1.0]],
            [[0.0, source_height - 1.0]],
        ],
        dtype=np.float64,
    )
    target_corners = cv2.perspectiveTransform(source_corners, matrix).reshape(-1, 2)
    if not np.all(np.isfinite(target_corners)):
        return False
    return _v2_corners_are_plausible(target_corners, target_shape)


def _fit_similarity_v2(
    source: NDArray[np.float64], target: NDArray[np.float64]
) -> tuple[NDArray[np.float64] | None, float]:
    rows = np.zeros((2 * len(source), 4), dtype=np.float64)
    values = np.zeros(2 * len(source), dtype=np.float64)
    rows[0::2, 0] = source[:, 0]
    rows[0::2, 1] = source[:, 1]
    rows[0::2, 2] = 1.0
    rows[1::2, 0] = source[:, 1]
    rows[1::2, 1] = -source[:, 0]
    rows[1::2, 3] = 1.0
    values[0::2] = target[:, 0]
    values[1::2] = target[:, 1]
    try:
        parameters, _, rank, _ = np.linalg.lstsq(rows, values, rcond=None)
    except np.linalg.LinAlgError:
        return None, math.inf
    if rank != 4 or not np.all(np.isfinite(parameters)):
        return None, math.inf
    scale_cosine, scale_sine, translation_x, translation_y = parameters
    matrix = np.asarray(
        (
            (scale_cosine, scale_sine, translation_x),
            (-scale_sine, scale_cosine, translation_y),
            (0.0, 0.0, 1.0),
        ),
        dtype=np.float64,
    )
    predicted = source @ matrix[:2, :2].T + matrix[:2, 2]
    rmse = float(np.sqrt(np.mean(np.sum((predicted - target) ** 2, axis=1))))
    if not math.isfinite(rmse):
        return None, math.inf
    return matrix, rmse


def _v2_corners_are_plausible(
    corners: NDArray[np.float64], target_shape: tuple[int, int]
) -> bool:
    target_height, target_width = target_shape
    x = corners[:, 0]
    y = corners[:, 1]
    signed_area = 0.5 * float(np.sum(x * np.roll(y, -1) - y * np.roll(x, -1)))
    target_area = max(1.0, float((target_width - 1) * (target_height - 1)))
    area_ratio = signed_area / target_area
    if not 0.0 < area_ratio <= _MAX_CORNER_AREA_RATIO:
        return False
    margin_x = _CORNER_MARGIN_FRACTION * target_width
    margin_y = _CORNER_MARGIN_FRACTION * target_height
    if (
        np.any(x < -margin_x)
        or np.any(x > target_width - 1 + margin_x)
        or np.any(y < -margin_y)
        or np.any(y > target_height - 1 + margin_y)
    ):
        return False

    target_polygon = np.asarray(
        (
            (0.0, 0.0),
            (target_width - 1.0, 0.0),
            (target_width - 1.0, target_height - 1.0),
            (0.0, target_height - 1.0),
        ),
        dtype=np.float32,
    )
    intersection_area, _ = cv2.intersectConvexConvex(
        corners.astype(np.float32), target_polygon
    )
    source_footprint_area = signed_area
    source_coverage = float(intersection_area) / max(1.0, source_footprint_area)
    target_coverage = float(intersection_area) / target_area
    return (
        source_coverage >= _MIN_CORNER_COVERAGE
        and target_coverage >= _MIN_CORNER_COVERAGE
    )


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
    *,
    source_shape: tuple[int, int] | None = None,
) -> NDArray[np.float64]:
    if source_shape is not None:
        return _synthesize_inter_area_view(
            source_shape,
            (height, width),
            frequencies,
            phases,
            amplitudes,
        )

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


def _synthesize_inter_area_view(
    source_shape: tuple[int, int],
    output_shape: tuple[int, int],
    frequencies: NDArray[np.float64],
    phases: NDArray[np.float64],
    amplitudes: NDArray[np.float64],
) -> NDArray[np.float64]:
    """Render the exact separable INTER_AREA view without a source raster."""

    source_height, source_width = source_shape
    output_height, output_width = output_shape
    spatial = np.zeros((output_height, output_width), dtype=np.float64)

    for (frequency_x, frequency_y), phase, amplitude in zip(
        frequencies, phases, amplitudes, strict=True
    ):
        wave_x = _inter_area_sinusoid_axis(
            source_width, output_width, float(frequency_x)
        )
        wave_y = _inter_area_sinusoid_axis(
            source_height, output_height, float(frequency_y)
        )
        cosine_x = wave_x.real
        sine_x = wave_x.imag
        cosine_y = wave_y.real
        sine_y = wave_y.imag
        cosine_phase = math.cos(float(phase))
        sine_phase = math.sin(float(phase))

        for start in range(0, output_height, _SYNTHESIS_ROW_CHUNK):
            stop = min(output_height, start + _SYNTHESIS_ROW_CHUNK)
            cosine_sum = cosine_y[start:stop, None] * cosine_x[None, :]
            cosine_sum -= sine_y[start:stop, None] * sine_x[None, :]
            sine_sum = sine_y[start:stop, None] * cosine_x[None, :]
            sine_sum += cosine_y[start:stop, None] * sine_x[None, :]
            spatial[start:stop] += float(amplitude) * (
                cosine_phase * cosine_sum - sine_phase * sine_sum
            )

    canonical_mean, canonical_rms = _canonical_spatial_statistics(
        source_shape, frequencies, phases, amplitudes
    )
    spatial -= canonical_mean
    spatial /= canonical_rms
    return spatial


def _inter_area_sinusoid_axis(
    source_length: int, output_length: int, frequency: float
) -> NDArray[np.complex128]:
    """Area-resample one discrete complex sinusoid with O(output) memory.

    Destination sample ``j`` averages source pixels over OpenCV's area cell.
    The edge construction deliberately follows OpenCV's floating-point
    ``fsx1 = j * scale`` then ``fsx2 = fsx1 + scale`` sequence: its strict
    1e-3 cutoff can differ from exact rational arithmetic at an endpoint.
    The fully covered interior is a finite geometric sum, so no
    canonical-length vector is materialized.
    """

    if source_length < output_length:
        raise ValueError("geometry pilot area view must not upsample")
    values = np.empty(output_length, dtype=np.complex128)
    two_pi = 2.0 * math.pi
    scale = source_length / output_length
    for output_index in range(output_length):
        left = output_index * scale
        right = left + scale
        cell_width = min(scale, source_length - left)
        first_interior = min(math.ceil(left), math.floor(right))
        right_boundary = min(math.floor(right), source_length - 1)
        first_interior = min(first_interior, right_boundary)
        weighted_sum = 0.0j
        if first_interior - left > _INTER_AREA_EDGE_EPSILON:
            weighted_sum = ((first_interior - left) / cell_width) * np.exp(
                1j * two_pi * frequency * (first_interior - 1)
            )
        interior_start = first_interior
        interior_count = max(0, right_boundary - first_interior)
        weighted_sum += _finite_exponential_sum(
            interior_start, interior_count, frequency
        ) / cell_width
        if right - right_boundary > _INTER_AREA_EDGE_EPSILON:
            right_weight = min(min(right - right_boundary, 1.0), cell_width)
            weighted_sum += (right_weight / cell_width) * np.exp(
                1j * two_pi * frequency * right_boundary
            )
        values[output_index] = weighted_sum
    return values


def _finite_exponential_sum(start: int, count: int, frequency: float) -> complex:
    if count <= 0:
        return 0.0j
    return (
        count
        * _finite_exponential_mean(count, frequency)
        * np.exp(2j * math.pi * frequency * start)
    )


def _canonical_spatial_statistics(
    shape: tuple[int, int],
    frequencies: NDArray[np.float64],
    phases: NDArray[np.float64],
    amplitudes: NDArray[np.float64],
) -> tuple[float, float]:
    """Return the exact discrete mean and centered RMS of the source pilot."""

    height, width = shape

    def complex_mean(frequency_x: float, frequency_y: float, phase: float) -> complex:
        return (
            np.exp(1j * phase)
            * _finite_exponential_mean(width, frequency_x)
            * _finite_exponential_mean(height, frequency_y)
        )

    mean = 0.0
    mean_square = 0.0
    for frequency_i, phase_i, amplitude_i in zip(
        frequencies, phases, amplitudes, strict=True
    ):
        mean += float(amplitude_i) * complex_mean(
            float(frequency_i[0]), float(frequency_i[1]), float(phase_i)
        ).real
        for frequency_j, phase_j, amplitude_j in zip(
            frequencies, phases, amplitudes, strict=True
        ):
            difference = complex_mean(
                float(frequency_i[0] - frequency_j[0]),
                float(frequency_i[1] - frequency_j[1]),
                float(phase_i - phase_j),
            ).real
            total = complex_mean(
                float(frequency_i[0] + frequency_j[0]),
                float(frequency_i[1] + frequency_j[1]),
                float(phase_i + phase_j),
            ).real
            mean_square += (
                0.5 * float(amplitude_i) * float(amplitude_j) * (difference + total)
            )

    variance = mean_square - mean * mean
    rms = math.sqrt(max(0.0, variance))
    if not math.isfinite(rms) or rms <= 0.0:
        raise ValueError("derived pilot has zero or non-finite energy")
    return mean, rms


def _finite_exponential_mean(length: int, frequency: float) -> complex:
    amplitude = np.sinc(length * frequency) / np.sinc(frequency)
    phase = math.pi * frequency * (length - 1)
    return complex(amplitude * np.exp(1j * phase))


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
