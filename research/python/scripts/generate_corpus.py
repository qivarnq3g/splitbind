"""Generate the deterministic, synthetic SplitBind acceptance corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import struct
import zlib
from pathlib import Path


GENERATOR_NAME = "splitbind-synthetic-corpus"
GENERATOR_VERSION = "1.0.0"
LICENSE = "CC0-1.0"
MAX_FIXTURE_BYTES = 2_000_000
PDF_WIDTH_POINTS = 612
PDF_HEIGHT_POINTS = 792


def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", checksum)


def grayscale_pixels(width: int, height: int, seed: int, style: str) -> bytes:
    rng = random.Random(seed)
    pixels = bytearray(width * height)
    for y in range(height):
        for x in range(width):
            gradient = (x * 173 // max(width - 1, 1) + y * 67 // max(height - 1, 1)) % 256
            if style == "gradient":
                value = gradient
            elif style == "noise":
                value = rng.randrange(256)
            elif style == "mixed":
                noise = rng.randrange(-36, 37)
                value = max(0, min(255, gradient + noise))
            elif style == "tamper":
                value = gradient
                if width // 5 <= x < width // 2 and height // 4 <= y < height // 2:
                    value = 245 if (x // 12 + y // 12) % 2 else 25
            else:
                raise ValueError(f"Unknown image style: {style}")
            pixels[y * width + x] = value
    return bytes(pixels)


def encode_grayscale_png(width: int, height: int, pixels: bytes) -> bytes:
    if len(pixels) != width * height:
        raise ValueError("Pixel count does not match dimensions")
    scanlines = b"".join(
        b"\x00" + pixels[row * width : (row + 1) * width] for row in range(height)
    )
    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", header)
        + png_chunk(b"IDAT", zlib.compress(scanlines, level=9))
        + png_chunk(b"IEND", b"")
    )


def pdf_stream(dictionary: str, data: bytes) -> bytes:
    prefix = f"<< {dictionary} /Length {len(data)} >>\nstream\n".encode("ascii")
    return prefix + data + b"\nendstream"


def escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(page_count: int, seed: int, style: str, fixture_id: str) -> bytes:
    objects: list[bytes] = [b"", b""]
    font_id = 3
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    page_ids: list[int] = []

    for page_index in range(page_count):
        image_seed = seed + page_index * 7919
        image_pixels = grayscale_pixels(160, 120, image_seed, "noise" if style == "noise" else "mixed")
        compressed_image = zlib.compress(image_pixels, level=9)
        page_id = len(objects) + 1
        content_id = page_id + 1
        image_id = page_id + 2
        page_ids.append(page_id)

        page = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PDF_WIDTH_POINTS} {PDF_HEIGHT_POINTS}] "
            f"/Resources << /Font << /F1 {font_id} 0 R >> /XObject << /Im0 {image_id} 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        ).encode("ascii")

        title = escape_pdf_text("SPLITBIND SYNTHETIC FIXTURE")
        label = escape_pdf_text(f"{fixture_id} PAGE {page_index + 1} OF {page_count}")
        if style == "whitespace":
            drawing = "0.92 g 48 650 516 72 re f 0.25 g 48 100 120 40 re f"
            image_transform = "160 0 0 120 390 110"
        elif style == "mixed":
            drawing = "0.94 g 48 620 516 90 re f 0.15 g 48 520 150 55 re f 0.55 g 220 520 150 55 re f"
            image_transform = "300 0 0 225 156 235"
        else:
            drawing = "0.90 g 48 620 516 90 re f 0.35 g 48 160 90 360 re f 0.70 g 474 160 90 360 re f"
            image_transform = "300 0 0 225 156 255"
        content = (
            f"{drawing}\n"
            f"BT /F1 18 Tf 60 724 Td ({title}) Tj ET\n"
            f"BT /F1 10 Tf 60 704 Td ({label}) Tj ET\n"
            f"q {image_transform} cm /Im0 Do Q\n"
        ).encode("ascii")
        image = pdf_stream(
            "/Type /XObject /Subtype /Image /Width 160 /Height 120 "
            "/ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode",
            compressed_image,
        )
        objects.extend([page, pdf_stream("", content), image])

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode("ascii")

    result = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_id, body in enumerate(objects, start=1):
        offsets.append(len(result))
        result.extend(f"{object_id} 0 obj\n".encode("ascii"))
        result.extend(body)
        result.extend(b"\nendobj\n")
    xref_offset = len(result)
    result.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    result.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        result.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    result.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(result)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def entry(
    output: Path,
    fixture_id: str,
    kind: str,
    filename: str,
    seed: int,
    pages: int,
    width: int,
    height: int,
    unit: str,
    **extra: object,
) -> dict:
    path = output / filename
    if path.stat().st_size > MAX_FIXTURE_BYTES:
        raise ValueError(f"Fixture exceeds {MAX_FIXTURE_BYTES} bytes: {filename}")
    value = {
        "fixture_id": fixture_id,
        "kind": kind,
        "relative_path": f"generated/{filename}",
        "generator_version": GENERATOR_VERSION,
        "generator_seed": seed,
        "pages": pages,
        "dimensions": {"width": width, "height": height, "unit": unit},
        "sha256": file_sha256(path),
        "license": LICENSE,
    }
    value.update(extra)
    return value


def generate(seed: int, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    entries: list[dict] = []
    pdf_specs = [
        ("pdf-one-vector", "clean-one-page-vector.pdf", 1, "mixed"),
        ("pdf-one-gradient", "clean-one-page-gradient.pdf", 1, "gradient"),
        ("pdf-one-whitespace", "clean-one-page-whitespace.pdf", 1, "whitespace"),
        ("pdf-multi-mixed", "clean-multi-page-mixed.pdf", 3, "mixed"),
        ("pdf-multi-noise", "clean-multi-page-noise.pdf", 2, "noise"),
    ]
    for index, (fixture_id, filename, pages, style) in enumerate(pdf_specs):
        item_seed = seed + index
        (output / filename).write_bytes(make_pdf(pages, item_seed, style, fixture_id))
        entries.append(
            entry(
                output,
                fixture_id,
                "clean_pdf",
                filename,
                item_seed,
                pages,
                PDF_WIDTH_POINTS,
                PDF_HEIGHT_POINTS,
                "points",
                content_features=["vector_text", "grayscale_shapes", style, "synthetic_raster"],
            )
        )

    clean_specs = [
        ("image-clean-gradient", "clean-gradient.png", "gradient"),
        ("image-clean-noise", "clean-noise.png", "noise"),
        ("image-clean-mixed", "clean-mixed-contrast.png", "mixed"),
    ]
    for index, (fixture_id, filename, style) in enumerate(clean_specs, start=20):
        item_seed = seed + index
        pixels = grayscale_pixels(640, 480, item_seed, style)
        (output / filename).write_bytes(encode_grayscale_png(640, 480, pixels))
        entries.append(
            entry(output, fixture_id, "clean_image", filename, item_seed, 1, 640, 480, "pixels")
        )

    for index in range(10):
        item_seed = seed + 100 + index
        filename = f"negative-external-{index:02d}.png"
        pixels = grayscale_pixels(512, 384, item_seed, "mixed" if index % 2 else "noise")
        (output / filename).write_bytes(encode_grayscale_png(512, 384, pixels))
        entries.append(
            entry(
                output,
                f"negative-external-{index:02d}",
                "negative_external",
                filename,
                item_seed,
                1,
                512,
                384,
                "pixels",
            )
        )

    tamper_seed = seed + 200
    tamper_name = "tamper-ground-truth.png"
    tamper_pixels = grayscale_pixels(640, 480, tamper_seed, "tamper")
    (output / tamper_name).write_bytes(encode_grayscale_png(640, 480, tamper_pixels))
    entries.append(
        entry(
            output,
            "tamper-ground-truth",
            "tamper_ground_truth",
            tamper_name,
            tamper_seed,
            1,
            640,
            480,
            "pixels",
            ground_truth_regions=[{"x": 0.2, "y": 0.25, "width": 0.3, "height": 0.25}],
        )
    )

    manifest = {
        "schema_version": 1,
        "generator": {"name": GENERATOR_NAME, "version": GENERATOR_VERSION, "seed": seed},
        "license": LICENSE,
        "max_fixture_bytes": MAX_FIXTURE_BYTES,
        "entries": entries,
    }
    manifest_path = output.parent / "corpus-manifest.v1.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = generate(args.seed, args.output)
    print(f"generated {len(manifest['entries'])} fixtures in {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
