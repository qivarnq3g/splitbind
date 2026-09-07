"""Bounded research acceptance check of source versus final PDF, not G1 proof."""

from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path

import numpy as np
import pypdfium2 as pdfium
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from splitbind_bench.metrics import compute_quality_metrics


MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 50
DPI = 144
MAX_PAGE_PIXELS = 4_000_000
MAX_DOCUMENT_PIXELS = 40_000_000


def _open_document(data: bytes, stack: ExitStack) -> pdfium.PdfDocument:
    if not isinstance(data, bytes) or not data.startswith(b"%PDF-"):
        raise ValueError("invalid_pdf")
    if len(data) > MAX_BYTES:
        raise ValueError("file_budget")
    try:
        document = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as error:
        raise ValueError("invalid_or_encrypted_pdf") from error
    stack.callback(document.close)
    document.init_forms()
    if not 1 <= len(document) <= MAX_PAGES:
        raise ValueError("page_budget")
    return document


def _user_units(data: bytes, page_count: int) -> list[float]:
    try:
        with BytesIO(data) as stream:
            reader = PdfReader(stream, strict=True)
            if reader.is_encrypted or len(reader.pages) != page_count:
                raise ValueError("unsupported_pdf")
            units = [float(page.user_unit) for page in reader.pages]
    except (PyPdfError, TypeError, OverflowError) as error:
        raise ValueError("invalid_pdf_units") from error
    if any(not math.isfinite(unit) or not 0 < unit <= 75000 for unit in units):
        raise ValueError("invalid_pdf_units")
    return units


def _sizes(document: pdfium.PdfDocument, units: list[float]) -> list[list[float]]:
    sizes = [
        [value * units[index] for value in document.get_page_size(index)]
        for index in range(len(document))
    ]
    if any(not math.isfinite(value) or value <= 0 for size in sizes for value in size):
        raise ValueError("invalid_page_geometry")
    return sizes


def _render(document: pdfium.PdfDocument, index: int, unit: float) -> np.ndarray:
    with ExitStack() as stack:
        page = document[index]
        stack.callback(page.close)
        bitmap = page.render(scale=DPI / 72 * unit, fill_color=(255, 255, 255, 255), draw_annots=True)
        stack.callback(bitmap.close)
        return np.asarray(bitmap.to_numpy(), dtype=np.uint8)[..., :3].copy()


def assess_pdf_fidelity(source_pdf: bytes, output_pdf: bytes) -> dict:
    """Compare visible geometry and pixels; do not normalize a changed layout.

    Measures visible page dimensions (CropBox/rotation as rendered), not every
    PDF box, text accessibility, print color, or vector fidelity at arbitrary
    zoom. Geometry-rejected pages are not rendered. Neither source nor output
    is changed. The byte ceiling applies to both files in this research tool.
    """
    with ExitStack() as stack:
        source = _open_document(source_pdf, stack)
        output = _open_document(output_pdf, stack)
        source_units = _user_units(source_pdf, len(source))
        output_units = _user_units(output_pdf, len(output))
        source_sizes, output_sizes = _sizes(source, source_units), _sizes(output, output_units)
        report = {
            "schema_version": 1,
            "dpi": DPI,
            "source_bytes": len(source_pdf),
            "output_bytes": len(output_pdf),
            "source_sha256": hashlib.sha256(source_pdf).hexdigest(),
            "output_sha256": hashlib.sha256(output_pdf).hexdigest(),
            "source_pages": len(source),
            "output_pages": len(output),
            "passed": False,
            "failures": [],
            "pages": [],
        }
        if len(source) != len(output):
            report["failures"].append("page_count")
            return report

        # Preflight all comparable pages before allocating raster buffers.
        totals = [0, 0]
        for index, (first_size, second_size) in enumerate(zip(source_sizes, output_sizes)):
            geometry_ok = all(abs(a - b) <= 0.01 for a, b in zip(first_size, second_size))
            page_report = {
                "page_index": index,
                "source_size_pt": first_size,
                "output_size_pt": second_size,
                "geometry_matches": geometry_ok,
                "identical_pixels": None,
                "psnr_db": None,
                "ssim": None,
            }
            report["pages"].append(page_report)
            if not geometry_ok:
                if "page_geometry" not in report["failures"]:
                    report["failures"].append("page_geometry")
                continue
            for which, size in enumerate((first_size, second_size)):
                pixels = math.ceil(size[0] * DPI / 72) * math.ceil(size[1] * DPI / 72)
                totals[which] += pixels
                if pixels > MAX_PAGE_PIXELS or totals[which] > MAX_DOCUMENT_PIXELS:
                    raise ValueError("raster_budget")

        for page_report in report["pages"]:
            if not page_report["geometry_matches"]:
                continue
            index = page_report["page_index"]
            first = _render(source, index, source_units[index])
            second = _render(output, index, output_units[index])
            if first.shape != second.shape:
                # Even a sub-point difference can cross a raster boundary.
                if "raster_geometry" not in report["failures"]:
                    report["failures"].append("raster_geometry")
                del first, second
                continue
            quality = compute_quality_metrics(first, second)
            identical = bool(np.array_equal(first, second))
            page_report.update(
                identical_pixels=identical,
                psnr_db=None if identical else quality.psnr_db,
                ssim=quality.ssim,
            )
            if (
                not math.isfinite(quality.ssim)
                or (not identical and not math.isfinite(quality.psnr_db))
                or quality.psnr_db < 38
                or quality.ssim < 0.95
            ):
                if "visual_quality" not in report["failures"]:
                    report["failures"].append("visual_quality")
            del first, second
        report["passed"] = not report["failures"]
        return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    try:
        # Bounded reads also apply if a file grows after opening.
        with args.source.open("rb") as stream:
            source = stream.read(MAX_BYTES + 1)
        with args.output.open("rb") as stream:
            output = stream.read(MAX_BYTES + 1)
        report = assess_pdf_fidelity(source, output)
        print(json.dumps(report, allow_nan=False, sort_keys=True))
        return 0 if report["passed"] else 2
    except (OSError, ValueError, pdfium.PdfiumError):
        # No input paths, document text or parser diagnostics in public output.
        print(json.dumps({"passed": False, "error": "measurement_failed"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
