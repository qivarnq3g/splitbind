"""Deterministic ORB/RANSAC page synchronization for reference decoding."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np
from numpy.typing import NDArray


UInt8Image = NDArray[np.uint8]
Float32Points = NDArray[np.float32]


@dataclass(frozen=True, slots=True)
class SyncTemplate:
    page_shape: tuple[int, int]
    keypoints: Float32Points
    descriptors: UInt8Image


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
    keypoints, descriptors = _detect(_to_gray(page))
    if descriptors is None or len(keypoints) < 4:
        raise ValueError("page has insufficient features for an ORB sync template")
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
    if not isinstance(sync_template, SyncTemplate):
        raise TypeError("sync_template must be a SyncTemplate")

    keypoints, descriptors = _detect(_to_gray(page))
    if descriptors is None or len(keypoints) < 4:
        return AlignmentResult(None, None, 0, 0, "insufficient_features")

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    pairs = matcher.knnMatch(descriptors, sync_template.descriptors, k=2)
    matches = [
        first
        for pair in pairs
        if len(pair) == 2
        for first, second in [pair]
        if first.distance < 0.75 * second.distance
    ]
    if len(matches) < 4:
        return AlignmentResult(None, None, len(matches), 0, "insufficient_matches")

    source = np.asarray(
        [keypoints[match.queryIdx].pt for match in matches], dtype=np.float64
    ).reshape(-1, 1, 2)
    target = np.asarray(
        [sync_template.keypoints[match.trainIdx] for match in matches],
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
    if inliers < 4:
        return AlignmentResult(None, None, len(matches), inliers, "geometry_failure")

    height, width = sync_template.page_shape
    aligned = cv2.warpPerspective(
        page,
        homography,
        (width, height),
        # Nearest-neighbor avoids a second low-pass interpolation before the
        # high-frequency QIM extractor.  A4 measures attack-specific behavior.
        flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_REFLECT_101,
    )
    return AlignmentResult(
        image=np.ascontiguousarray(aligned, dtype=np.uint8),
        homography=np.asarray(homography, dtype=np.float64),
        matched_keypoints=len(matches),
        inlier_keypoints=inliers,
        reason="aligned",
    )


def _detect(gray: UInt8Image):
    cv2.setRNGSeed(0)
    detector = cv2.ORB_create(
        nfeatures=1500,
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
    return np.ascontiguousarray(page_bgr)
