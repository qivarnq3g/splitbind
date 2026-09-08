"""Deterministic ORB/RANSAC page synchronization for reference decoding."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np
from numpy.typing import NDArray


UInt8Image = NDArray[np.uint8]
Float32Points = NDArray[np.float32]
_MAX_PAGE_PIXELS = 40_000_000
_ORB_NFEATURES = 1500
_MIN_INLIERS = 8
_MIN_INLIER_RATIO = 0.35
_MIN_SPATIAL_COVERAGE = 0.05
_MAX_HOMOGRAPHY_CONDITION = 100_000.0
_MIN_AFFINE_DETERMINANT = 0.25
_MAX_AFFINE_DETERMINANT = 4.0
_MAX_REPROJECTION_RMSE_PX = 3.0
_MIN_CORNER_AREA_RATIO = 0.25
_MAX_CORNER_AREA_RATIO = 4.0
_CORNER_MARGIN_RATIO = 0.50


@dataclass(frozen=True, slots=True)
class SyncTemplate:
    page_shape: tuple[int, int]
    keypoints: Float32Points
    descriptors: UInt8Image

    def __post_init__(self) -> None:
        height, width = _validate_page_shape(self.page_shape)
        points, descriptors = _validate_orb_arrays(self.keypoints, self.descriptors)
        object.__setattr__(self, "page_shape", (height, width))
        object.__setattr__(self, "keypoints", points)
        object.__setattr__(self, "descriptors", descriptors)


@dataclass(frozen=True, slots=True)
class AlignmentResult:
    image: UInt8Image | None
    homography: NDArray[np.float64] | None
    matched_keypoints: int
    inlier_keypoints: int
    reason: Literal[
        "aligned", "insufficient_features", "insufficient_matches", "geometry_failure"
    ]


def build_sync_template(page_bgr: UInt8Image) -> SyncTemplate:
    """Capture stable ORB descriptors and coordinates for a canonical page."""

    page = _validate_page(page_bgr)
    try:
        keypoints, descriptors = _detect(_to_gray(page))
    except cv2.error as error:
        raise ValueError("OpenCV could not build a sync template") from error
    if descriptors is None or len(keypoints) < 4:
        raise ValueError("page has insufficient features for an ORB sync template")
    keypoints = keypoints[:_ORB_NFEATURES]
    descriptors = descriptors[:_ORB_NFEATURES]
    points = np.asarray([point.pt for point in keypoints], dtype=np.float32)
    points.setflags(write=False)
    frozen_descriptors = np.ascontiguousarray(descriptors, dtype=np.uint8)
    frozen_descriptors.setflags(write=False)
    return SyncTemplate(
        page_shape=page.shape[:2],
        keypoints=points,
        descriptors=frozen_descriptors,
    )


def align_page(page_bgr: UInt8Image, sync_template: SyncTemplate) -> AlignmentResult:
    """Map an attacked page into template coordinates using ORB and RANSAC."""

    page = _validate_page(page_bgr)
    template = validate_sync_template(sync_template)
    try:
        keypoints, descriptors = _detect(_to_gray(page))
        if descriptors is None or len(keypoints) < 4:
            return AlignmentResult(None, None, 0, 0, "insufficient_features")

        matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
        pairs = matcher.knnMatch(descriptors, template.descriptors, k=2)
        matches = [
            first
            for pair in pairs
            if len(pair) == 2
            for first, second in [pair]
            if first.distance < 0.75 * second.distance
        ]
        if len(matches) < _MIN_INLIERS:
            return AlignmentResult(None, None, len(matches), 0, "insufficient_matches")

        source = np.asarray(
            [keypoints[match.queryIdx].pt for match in matches], dtype=np.float64
        ).reshape(-1, 1, 2)
        target = np.asarray(
            [template.keypoints[match.trainIdx] for match in matches],
            dtype=np.float64,
        ).reshape(-1, 1, 2)
        cv2.setRNGSeed(0)
        homography, inlier_mask = cv2.findHomography(
            source,
            target,
            method=cv2.RANSAC,
            ransacReprojThreshold=3.0,
            maxIters=2000,
            confidence=0.995,
        )
        if homography is None or inlier_mask is None:
            return AlignmentResult(None, None, len(matches), 0, "geometry_failure")
        inliers = int(np.count_nonzero(inlier_mask))
        if not _geometry_is_acceptable(
            homography,
            source,
            target,
            inlier_mask,
            page.shape[:2],
            template.page_shape,
        ):
            return AlignmentResult(None, None, len(matches), inliers, "geometry_failure")
        homography = np.asarray(homography, dtype=np.float64)
        homography = homography / homography[2, 2]

        height, width = template.page_shape
        aligned = cv2.warpPerspective(
            page,
            homography,
            (width, height),
            # Nearest-neighbor avoids a second low-pass interpolation before the
            # high-frequency QIM extractor.  A4 measures attack-specific behavior.
            flags=cv2.INTER_NEAREST,
            borderMode=cv2.BORDER_REFLECT_101,
        )
    except cv2.error:
        return AlignmentResult(None, None, 0, 0, "geometry_failure")
    return AlignmentResult(
        image=np.ascontiguousarray(aligned, dtype=np.uint8),
        homography=np.asarray(homography, dtype=np.float64),
        matched_keypoints=len(matches),
        inlier_keypoints=inliers,
        reason="aligned",
    )


def _geometry_is_acceptable(
    homography: object,
    source: NDArray[np.float64],
    target: NDArray[np.float64],
    inlier_mask: object,
    source_shape: tuple[int, int],
    target_shape: tuple[int, int],
) -> bool:
    """Apply deterministic, measured gates before allocating a warped raster.

    Eight inliers is twice the mathematical minimum.  The 3 px error ceiling
    matches RANSAC's configured reprojection threshold; the remaining bounds
    reject spatially clustered, reflected, ill-conditioned, or off-page fits
    while retaining the seeded 3-degree/translation reference case.
    """

    matrix = np.asarray(homography)
    mask = np.asarray(inlier_mask)
    if matrix.shape != (3, 3) or mask.size != source.shape[0]:
        return False
    if not np.all(np.isfinite(matrix)) or abs(float(matrix[2, 2])) <= 1e-12:
        return False
    matrix = matrix.astype(np.float64) / float(matrix[2, 2])
    condition = float(np.linalg.cond(matrix))
    if not math.isfinite(condition) or condition > _MAX_HOMOGRAPHY_CONDITION:
        return False

    inlier_selection = mask.reshape(-1).astype(bool)
    inlier_count = int(np.count_nonzero(inlier_selection))
    if inlier_count < _MIN_INLIERS:
        return False
    if inlier_count / source.shape[0] < _MIN_INLIER_RATIO:
        return False

    source_inliers = source.reshape(-1, 2)[inlier_selection]
    target_inliers = target.reshape(-1, 2)[inlier_selection]
    if not np.all(np.isfinite(source_inliers)) or not np.all(np.isfinite(target_inliers)):
        return False
    if _spatial_coverage(source_inliers, source_shape) < _MIN_SPATIAL_COVERAGE:
        return False
    if _spatial_coverage(target_inliers, target_shape) < _MIN_SPATIAL_COVERAGE:
        return False

    affine_determinant = float(np.linalg.det(matrix[:2, :2]))
    if not _MIN_AFFINE_DETERMINANT <= affine_determinant <= _MAX_AFFINE_DETERMINANT:
        return False

    projected = cv2.perspectiveTransform(
        source_inliers.reshape(-1, 1, 2), matrix
    ).reshape(-1, 2)
    if not np.all(np.isfinite(projected)):
        return False
    rmse = float(np.sqrt(np.mean(np.sum((projected - target_inliers) ** 2, axis=1))))
    if not math.isfinite(rmse) or rmse > _MAX_REPROJECTION_RMSE_PX:
        return False

    source_height, source_width = source_shape
    corners = np.asarray(
        [
            [[0.0, 0.0]],
            [[source_width - 1.0, 0.0]],
            [[source_width - 1.0, source_height - 1.0]],
            [[0.0, source_height - 1.0]],
        ],
        dtype=np.float64,
    )
    transformed_corners = cv2.perspectiveTransform(corners, matrix).reshape(-1, 2)
    return _corners_are_plausible(transformed_corners, target_shape)


def _spatial_coverage(points: NDArray[np.float64], shape: tuple[int, int]) -> float:
    height, width = shape
    span = np.ptp(points, axis=0)
    page_area = max(1.0, float((width - 1) * (height - 1)))
    return float(span[0] * span[1] / page_area)


def _corners_are_plausible(
    corners: NDArray[np.float64], target_shape: tuple[int, int]
) -> bool:
    if corners.shape != (4, 2) or not np.all(np.isfinite(corners)):
        return False
    height, width = target_shape
    margin_x = _CORNER_MARGIN_RATIO * width
    margin_y = _CORNER_MARGIN_RATIO * height
    if (
        np.any(corners[:, 0] < -margin_x)
        or np.any(corners[:, 0] > width - 1 + margin_x)
        or np.any(corners[:, 1] < -margin_y)
        or np.any(corners[:, 1] > height - 1 + margin_y)
    ):
        return False
    x = corners[:, 0]
    y = corners[:, 1]
    signed_area = 0.5 * float(np.sum(x * np.roll(y, -1) - y * np.roll(x, -1)))
    target_area = max(1.0, float((width - 1) * (height - 1)))
    area_ratio = signed_area / target_area
    return _MIN_CORNER_AREA_RATIO <= area_ratio <= _MAX_CORNER_AREA_RATIO


def _detect(gray: UInt8Image):
    cv2.setRNGSeed(0)
    detector = cv2.ORB_create(
        nfeatures=_ORB_NFEATURES,
        scaleFactor=1.2,
        nlevels=8,
        edgeThreshold=15,
        firstLevel=0,
        WTA_K=2,
        scoreType=cv2.ORB_HARRIS_SCORE,
        patchSize=31,
        fastThreshold=10,
    )
    return detector.detectAndCompute(gray, None)


def _to_gray(page_bgr: UInt8Image) -> UInt8Image:
    luminance = (
        0.114 * page_bgr[..., 0].astype(np.float64)
        + 0.587 * page_bgr[..., 1].astype(np.float64)
        + 0.299 * page_bgr[..., 2].astype(np.float64)
    )
    return np.floor(luminance + 0.5).clip(0, 255).astype(np.uint8)


def _validate_page(page_bgr: UInt8Image) -> UInt8Image:
    if not isinstance(page_bgr, np.ndarray):
        raise TypeError("page must be a numpy array")
    if page_bgr.ndim != 3 or page_bgr.shape[2] != 3:
        raise ValueError("page must have BGR shape (height, width, 3)")
    if page_bgr.dtype != np.uint8:
        raise TypeError("synchronization page dtype must be uint8")
    if page_bgr.shape[0] == 0 or page_bgr.shape[1] == 0:
        raise ValueError("page must have non-empty dimensions")
    if page_bgr.shape[0] * page_bgr.shape[1] > _MAX_PAGE_PIXELS:
        raise ValueError("page must contain at most 40,000,000 pixels")
    return np.ascontiguousarray(page_bgr)


def validate_sync_template(sync_template: SyncTemplate) -> SyncTemplate:
    """Validate and defensively copy a template at a trust boundary."""

    if not isinstance(sync_template, SyncTemplate):
        raise TypeError("sync_template must be a SyncTemplate")
    return SyncTemplate(
        sync_template.page_shape,
        sync_template.keypoints,
        sync_template.descriptors,
    )


def _validate_page_shape(page_shape: object) -> tuple[int, int]:
    if not isinstance(page_shape, tuple) or len(page_shape) != 2:
        raise ValueError("page_shape must contain two positive integers")
    height, width = page_shape
    if any(
        not isinstance(value, int) or isinstance(value, bool) or value <= 0
        for value in (height, width)
    ):
        raise ValueError("page_shape must contain two positive integers")
    if height * width > _MAX_PAGE_PIXELS:
        raise ValueError("page_shape must contain at most 40,000,000 pixels")
    return height, width


def _validate_orb_arrays(
    keypoints: object, descriptors: object
) -> tuple[Float32Points, UInt8Image]:
    if not isinstance(keypoints, np.ndarray) or keypoints.dtype != np.float32:
        raise ValueError("keypoints must have float32 dtype")
    if keypoints.ndim != 2 or keypoints.shape[1:] != (2,):
        raise ValueError("keypoints must have shape N x 2")
    if not np.all(np.isfinite(keypoints)):
        raise ValueError("keypoints must contain only finite coordinates")
    if not isinstance(descriptors, np.ndarray) or descriptors.dtype != np.uint8:
        raise ValueError("descriptors must have uint8 dtype")
    if descriptors.ndim != 2 or descriptors.shape[1:] != (32,):
        raise ValueError("descriptors must have shape N x 32")
    if descriptors.shape[0] != keypoints.shape[0]:
        raise ValueError("descriptors must have a count matching keypoints")
    if not 4 <= keypoints.shape[0] <= _ORB_NFEATURES:
        raise ValueError("ORB point count must be between 4 and 1500")
    frozen_points = np.array(keypoints, dtype=np.float32, order="C", copy=True)
    frozen_descriptors = np.array(descriptors, dtype=np.uint8, order="C", copy=True)
    frozen_points.setflags(write=False)
    frozen_descriptors.setflags(write=False)
    return frozen_points, frozen_descriptors
