"""Deterministic image attacks defined by the versioned A1 matrix."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping

import cv2
import numpy as np
from numpy.typing import NDArray

from .ground_truth import (
    IDENTITY_TRANSFORM,
    NormalizedRect,
    Transform,
    compose_transforms,
    merge_regions,
    transform_regions,
)


Image = NDArray[np.uint8]


@dataclass(frozen=True, slots=True)
class AttackCase:
    case_id: str
    kind: str
    parameters: Mapping[str, object]
    operations: tuple["AttackCase", ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class AttackedArtifact:
    image: Image
    ground_truth: tuple[NormalizedRect, ...] = ()
    operations: tuple[str, ...] = ()
    retained_region: NormalizedRect | None = None
    removed_area_fraction: float = 0.0
    source_to_output: Transform = IDENTITY_TRANSFORM


def apply_attack(
    image: Image, case: AttackCase, rng: np.random.Generator
) -> AttackedArtifact:
    """Apply one contracted attack without mutating the source raster."""

    source = _validate_image(image)
    if not isinstance(case, AttackCase):
        raise TypeError("case must be an AttackCase")
    if not isinstance(rng, np.random.Generator):
        raise TypeError("rng must be a numpy Generator")
    if case.kind == "identity":
        if case.parameters or case.operations:
            raise ValueError("identity attack must not contain parameters or operations")
        return AttackedArtifact(
            image=np.ascontiguousarray(source).copy(),
            operations=("identity",),
            source_to_output=IDENTITY_TRANSFORM,
        )
    if case.kind == "combined":
        if not case.operations:
            raise ValueError("combined attack must contain ordered operations")
        current = AttackedArtifact(image=source.copy())
        ordered: list[str] = []
        ground_truth: tuple[NormalizedRect, ...] = ()
        source_to_output = IDENTITY_TRANSFORM
        retained_region: NormalizedRect | None = None
        removed_fraction = 0.0
        for operation in case.operations:
            current = apply_attack(current.image, operation, rng)
            ordered.extend(current.operations)
            ground_truth = merge_regions(
                transform_regions(ground_truth, current.source_to_output),
                current.ground_truth,
            )
            source_to_output = compose_transforms(
                current.source_to_output, source_to_output
            )
            if current.retained_region is not None:
                retained_region = current.retained_region
                removed_fraction = 1.0 - (1.0 - removed_fraction) * (
                    1.0 - current.removed_area_fraction
                )
        return AttackedArtifact(
            image=current.image,
            ground_truth=ground_truth,
            operations=tuple(ordered),
            retained_region=retained_region,
            removed_area_fraction=removed_fraction,
            source_to_output=source_to_output,
        )

    handlers = {
        "jpeg": _jpeg_roundtrip,
        "crop": _crop_fraction,
        "resize": _resize_scale,
        "rotation": _rotate_degrees,
        "brightness_contrast": _adjust_brightness_contrast,
        "noise_blur": _add_noise_then_blur,
        "screenshot": _simulate_screenshot,
        "perspective": _perspective_warp,
        "tamper": _apply_tamper_with_ground_truth,
    }
    try:
        handler = handlers[case.kind]
    except KeyError as error:
        raise ValueError(f"unsupported attack kind: {case.kind}") from error
    artifact = handler(source, case.parameters, rng)
    return AttackedArtifact(
        image=np.ascontiguousarray(artifact.image),
        ground_truth=artifact.ground_truth,
        operations=(case.kind,),
        retained_region=artifact.retained_region,
        removed_area_fraction=artifact.removed_area_fraction,
        source_to_output=artifact.source_to_output,
    )


def planned_crop_geometry(
    case: AttackCase, page_shape: tuple[int, int]
) -> tuple[NormalizedRect, float] | None:
    """Return exact direct-crop geometry without constructing an image artifact."""

    if not isinstance(case, AttackCase):
        raise TypeError("case must be an AttackCase")
    if case.kind != "crop":
        return None
    _, _, _, _, retained, removed_fraction = _crop_geometry(case.parameters, page_shape)
    return retained, removed_fraction


def _jpeg_roundtrip(
    image: Image, parameters: Mapping[str, object], _: np.random.Generator
) -> AttackedArtifact:
    quality = _bounded_integer(parameters, "quality", 1, 100)
    encoded, buffer = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not encoded:
        raise RuntimeError("OpenCV failed to encode JPEG attack")
    decoded = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if decoded is None:
        raise RuntimeError("OpenCV failed to decode JPEG attack")
    return AttackedArtifact(decoded)


def _crop_fraction(
    image: Image, parameters: Mapping[str, object], _: np.random.Generator
) -> AttackedArtifact:
    x0, y0, retained_width, retained_height, retained, actual_fraction = _crop_geometry(
        parameters, image.shape[:2]
    )
    return AttackedArtifact(
        image=image[y0 : y0 + retained_height, x0 : x0 + retained_width].copy(),
        retained_region=retained,
        removed_area_fraction=actual_fraction,
        source_to_output=(
            1.0 / retained.width,
            0.0,
            -retained.x / retained.width,
            0.0,
            1.0 / retained.height,
            -retained.y / retained.height,
            0.0,
            0.0,
            1.0,
        ),
    )


def _crop_geometry(
    parameters: Mapping[str, object], page_shape: tuple[int, int]
) -> tuple[int, int, int, int, NormalizedRect, float]:
    if not isinstance(parameters, Mapping):
        raise TypeError("crop parameters must be a mapping")
    if (
        not isinstance(page_shape, tuple)
        or len(page_shape) != 2
        or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 1
            for value in page_shape
        )
    ):
        raise ValueError("crop page shape must be positive integer (height, width)")
    fraction = _bounded_float(parameters, "fraction", 0.0, 1.0, upper_inclusive=False)
    height, width = page_shape
    side_scale = math.sqrt(1.0 - fraction)
    retained_width = max(1, round(width * side_scale))
    retained_height = max(1, round(height * side_scale))
    x0 = (width - retained_width) // 2
    y0 = (height - retained_height) // 2
    actual_fraction = 1.0 - (retained_width * retained_height) / (width * height)
    retained = NormalizedRect(
        x=x0 / width,
        y=y0 / height,
        width=retained_width / width,
        height=retained_height / height,
    )
    return x0, y0, retained_width, retained_height, retained, actual_fraction


def _resize_scale(
    image: Image, parameters: Mapping[str, object], _: np.random.Generator
) -> AttackedArtifact:
    scale = _positive_float(parameters, "scale")
    height, width = image.shape[:2]
    target = (max(1, round(width * scale)), max(1, round(height * scale)))
    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
    return AttackedArtifact(cv2.resize(image, target, interpolation=interpolation))


def _rotate_degrees(
    image: Image, parameters: Mapping[str, object], _: np.random.Generator
) -> AttackedArtifact:
    degrees = _finite_float(parameters, "degrees")
    height, width = image.shape[:2]
    transform = cv2.getRotationMatrix2D(((width - 1) / 2.0, (height - 1) / 2.0), degrees, 1.0)
    rotated = cv2.warpAffine(
        image,
        transform,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REFLECT_101,
    )
    return AttackedArtifact(
        rotated,
        source_to_output=_pixel_transform_to_normalized(
            np.vstack((transform, (0.0, 0.0, 1.0))), width, height, width, height
        ),
    )


def _adjust_brightness_contrast(
    image: Image, parameters: Mapping[str, object], _: np.random.Generator
) -> AttackedArtifact:
    brightness = _positive_float(parameters, "brightness_factor")
    contrast = _positive_float(parameters, "contrast_factor")
    midpoint = 127.5
    changed = ((image.astype(np.float64) - midpoint) * contrast + midpoint) * brightness
    return AttackedArtifact(np.clip(np.floor(changed + 0.5), 0, 255).astype(np.uint8))


def _add_noise_then_blur(
    image: Image, parameters: Mapping[str, object], rng: np.random.Generator
) -> AttackedArtifact:
    noise_sigma = _bounded_float(parameters, "noise_sigma", 0.0, math.inf)
    blur_sigma = _bounded_float(parameters, "blur_sigma", 0.0, math.inf)
    noise = rng.normal(0.0, noise_sigma, size=image.shape)
    changed = np.clip(np.floor(image.astype(np.float64) + noise + 0.5), 0, 255).astype(np.uint8)
    if blur_sigma > 0.0:
        changed = cv2.GaussianBlur(changed, (0, 0), blur_sigma, borderType=cv2.BORDER_REFLECT_101)
    return AttackedArtifact(changed)


def _simulate_screenshot(
    image: Image, parameters: Mapping[str, object], rng: np.random.Generator
) -> AttackedArtifact:
    width = _bounded_integer(parameters, "width_px", 1, 16384)
    height = _bounded_integer(parameters, "height_px", 1, 16384)
    source_height, source_width = image.shape[:2]
    scale = min(width / source_width, height / source_height)
    content_width = max(1, round(source_width * scale))
    content_height = max(1, round(source_height * scale))
    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
    content = cv2.resize(image, (content_width, content_height), interpolation=interpolation)
    screen = np.full((height, width, 3), 32, dtype=np.uint8)
    x0 = (width - content_width) // 2
    y0 = (height - content_height) // 2
    screen[y0 : y0 + content_height, x0 : x0 + content_width] = content
    kind = parameters.get("kind")
    if kind == "raster":
        return AttackedArtifact(
            screen,
            source_to_output=(
                content_width / width,
                0.0,
                x0 / width,
                0.0,
                content_height / height,
                y0 / height,
                0.0,
                0.0,
                1.0,
            ),
        )
    if kind == "perspective":
        perspective = _perspective_warp(screen, parameters, rng)
        letterbox = (
            content_width / width,
            0.0,
            x0 / width,
            0.0,
            content_height / height,
            y0 / height,
            0.0,
            0.0,
            1.0,
        )
        return AttackedArtifact(
            perspective.image,
            source_to_output=compose_transforms(
                perspective.source_to_output, letterbox
            ),
        )
    raise ValueError("screenshot kind must be raster or perspective")


def _perspective_warp(
    image: Image, parameters: Mapping[str, object], _: np.random.Generator
) -> AttackedArtifact:
    raw_offsets = parameters.get("corner_offsets")
    offsets = np.asarray(raw_offsets, dtype=np.float64)
    if offsets.shape != (4, 2) or not np.all(np.isfinite(offsets)):
        raise ValueError("corner_offsets must contain four finite [x, y] pairs")
    height, width = image.shape[:2]
    corners = np.asarray(
        [[0.0, 0.0], [width - 1.0, 0.0], [width - 1.0, height - 1.0], [0.0, height - 1.0]],
        dtype=np.float32,
    )
    target = corners + offsets.astype(np.float32) * np.asarray([width, height], dtype=np.float32)
    transform = cv2.getPerspectiveTransform(corners, target)
    warped = cv2.warpPerspective(
        image,
        transform,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(24, 24, 24),
    )
    return AttackedArtifact(
        warped,
        source_to_output=_pixel_transform_to_normalized(
            transform, width, height, width, height
        ),
    )


def _apply_tamper_with_ground_truth(
    image: Image, parameters: Mapping[str, object], _: np.random.Generator
) -> AttackedArtifact:
    raw_region = parameters.get("region")
    if not isinstance(raw_region, Mapping):
        raise ValueError("tamper region must be a normalized rectangle mapping")
    try:
        region = NormalizedRect(
            float(raw_region["x"]),
            float(raw_region["y"]),
            float(raw_region["width"]),
            float(raw_region["height"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("tamper region must be a valid normalized rectangle") from error
    height, width = image.shape[:2]
    x0 = min(width - 1, max(0, round(region.x * width)))
    y0 = min(height - 1, max(0, round(region.y * height)))
    x1 = min(width, max(x0 + 1, round(region.right * width)))
    y1 = min(height, max(y0 + 1, round(region.bottom * height)))
    changed = image.copy()
    kind = parameters.get("kind")
    if kind == "replace_text":
        changed[y0:y1, x0:x1] = 245
        changed[y0:y1:3, x0:x1] = (20, 20, 20)
    elif kind == "cover_region":
        changed[y0:y1, x0:x1] = 0
    elif kind == "copy_move":
        region_width = x1 - x0
        source_x0 = max(0, x0 - region_width)
        if source_x0 == x0:
            source_x0 = min(width - region_width, x1)
        source = image[y0:y1, source_x0 : source_x0 + region_width]
        if source.shape != changed[y0:y1, x0:x1].shape:
            source = cv2.resize(source, (region_width, y1 - y0), interpolation=cv2.INTER_LINEAR)
        changed[y0:y1, x0:x1] = source
    elif kind == "insert_object":
        yy, xx = np.indices((y1 - y0, x1 - x0))
        checker = ((xx // 8 + yy // 8) % 2).astype(bool)
        changed[y0:y1, x0:x1][checker] = (16, 64, 224)
        changed[y0:y1, x0:x1][~checker] = (224, 192, 24)
    else:
        raise ValueError("unsupported tamper kind")
    return AttackedArtifact(changed, ground_truth=(region,))


def _validate_image(image: Image) -> Image:
    if not isinstance(image, np.ndarray):
        raise TypeError("image must be a numpy array")
    if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("image must have non-empty uint8 BGR shape")
    if image.shape[0] == 0 or image.shape[1] == 0:
        raise ValueError("image must have non-empty uint8 BGR shape")
    return np.ascontiguousarray(image)


def _pixel_transform_to_normalized(
    pixel_transform: NDArray[np.floating],
    source_width: int,
    source_height: int,
    output_width: int,
    output_height: int,
) -> Transform:
    source_scale = np.diag((source_width, source_height, 1.0))
    output_scale_inverse = np.diag((1.0 / output_width, 1.0 / output_height, 1.0))
    normalized = (
        output_scale_inverse
        @ np.asarray(pixel_transform, dtype=np.float64)
        @ source_scale
    )
    return tuple(float(value) for value in normalized.ravel())  # type: ignore[return-value]


def _finite_float(parameters: Mapping[str, object], name: str) -> float:
    value = parameters.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{name} must be a finite real number")
    return float(value)


def _positive_float(parameters: Mapping[str, object], name: str) -> float:
    value = _finite_float(parameters, name)
    if value <= 0.0:
        raise ValueError(f"{name} must be positive")
    return value


def _bounded_float(
    parameters: Mapping[str, object],
    name: str,
    lower: float,
    upper: float,
    *,
    upper_inclusive: bool = True,
) -> float:
    value = _finite_float(parameters, name)
    outside_upper = value > upper if upper_inclusive else value >= upper
    if value < lower or outside_upper:
        bracket = "]" if upper_inclusive else ")"
        raise ValueError(f"{name} must be in [{lower}, {upper}{bracket}")
    return value


def _bounded_integer(
    parameters: Mapping[str, object], name: str, lower: int, upper: int
) -> int:
    value = parameters.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
        raise ValueError(f"{name} must be an integer in [{lower}, {upper}]")
    return value
