from __future__ import annotations

import math
import os
import re
import tempfile
import time
import uuid
from pathlib import Path

import cv2
import numpy as np
import pypdfium2 as pdfium
from django.conf import settings
from django.db import transaction

from splitbind.demo.capabilities import DEMO_ALGORITHM_LABEL
from splitbind.demo.results import IssuanceProcessingResult
from splitbind.integrations.storage.base import StorageUnavailable, UploadRejected
from splitbind.jobs.models import Job, JobKind, JobResultReceipt, JobStatus
from splitbind.jobs.state import transition_job
from splitbind_ref.fingerprint_v2 import FingerprintV2Context, embed_fingerprint_v2
from splitbind_ref.fingerprint_v2_profile import candidate_identifier_v2, load_v2_profiles


DEMO_MAX_PDF_BYTES = 10 * 1024 * 1024
DEMO_MAX_PAGES = 5
DEMO_MAX_RASTER_PIXELS = 40_000_000
CANONICAL_CANVAS = (2304, 1152)
SOURCE_RENDER_SCALE = 2.0
FINGERPRINT_KEY_ENV = "SPLITBIND_DEMO_FINGERPRINT_KEY_HEX"
FROZEN_CANDIDATE_IDENTIFIER_HEX = (
    "5342463201e7490f80b69ef1a3289afce40ef02989c9a4d89f00b916055cbf1c4"
    "c83a97b880000000240380000000000003ff8000000000000000001800000001200"
    "00000300000003"
)
LIMITATIONS = (
    "fingerprint.experimental_unreleased_v2",
    "fingerprint.not_gate_g1_evidence",
    "evidence.not_proof_of_leak_edit_or_distribution",
)


class DemoIssuanceError(RuntimeError):
    def __init__(self, code: str, *, cleanup_failures: int = 0):
        super().__init__(code)
        self.code = code
        self.cleanup_failures = cleanup_failures


def process_issuance_job(*, job_id, storage) -> IssuanceProcessingResult:
    started = time.monotonic()
    job = Job.objects.select_related("issuance__document").get(pk=job_id)
    _validate_processing_job(job)
    if _cancel_before_work(job.id):
        raise DemoIssuanceError("DEMO_JOB_CANCELLED")

    try:
        return _process_issuance_job(job=job, storage=storage, started=started)
    except DemoIssuanceError as error:
        if error.code not in {
            "DEMO_JOB_CANCELLED",
            "DEMO_JOB_CANCELLED_OUTPUT_CLEANUP_FAILED",
        }:
            _record_failed_job(job.id, error.code)
        raise
    except Exception as error:
        wrapped = DemoIssuanceError("DEMO_ISSUANCE_PROCESSING_FAILED")
        _record_failed_job(job.id, wrapped.code)
        raise wrapped from error


def _process_issuance_job(*, job: Job, storage, started: float) -> IssuanceProcessingResult:
    issuance = job.issuance
    document = issuance.document
    fingerprint_key = _load_fingerprint_key()
    output_key = f"outputs/issuance/{job.organization_id}/{issuance.id}.pdf"
    workspace = tempfile.TemporaryDirectory(prefix=f"splitbind-demo-{job.id}-")
    workspace_path = Path(workspace.name)

    try:
        try:
            downloaded = storage.download_bytes(
                key=document.source_object_key,
                max_bytes=min(settings.MAX_PDF_BYTES, DEMO_MAX_PDF_BYTES),
                expected_sha256=document.expected_source_sha256,
            )
        except UploadRejected as error:
            code = (
                "DEMO_INPUT_CHECKSUM_MISMATCH"
                if str(error) == "STORAGE_CHECKSUM_MISMATCH"
                else "DEMO_PDF_FILE_LIMIT"
                if str(error) == "STORAGE_BYTE_LIMIT"
                else "DEMO_INPUT_STORAGE_REJECTED"
            )
            raise DemoIssuanceError(code) from error
        except StorageUnavailable as error:
            raise DemoIssuanceError("DEMO_INPUT_STORAGE_FAILED") from error

        source_path = workspace_path / "source.pdf"
        output_path = workspace_path / "output.pdf"
        source_path.write_bytes(downloaded.data)
        output_bytes, page_count, candidate_identifier = _build_issuance_pdf(
            source_path.read_bytes(),
            issuance_id=issuance.id,
            fingerprint_key=fingerprint_key,
        )
        output_path.write_bytes(output_bytes)
        try:
            with output_path.open("rb") as output_stream:
                uploaded = storage.upload_bytes(
                    key=output_key,
                    content_type="application/pdf",
                    chunks=iter(lambda: output_stream.read(64 * 1024), b""),
                    max_bytes=min(settings.MAX_PDF_BYTES, DEMO_MAX_PDF_BYTES),
                )
        except (StorageUnavailable, UploadRejected) as error:
            cleanup_failures = _compensate_output(storage, output_key)
            code = (
                "DEMO_OUTPUT_STORAGE_CLEANUP_FAILED"
                if cleanup_failures
                else "DEMO_OUTPUT_STORAGE_FAILED"
            )
            raise DemoIssuanceError(code, cleanup_failures=cleanup_failures) from error
    except Exception as error:
        workspace_cleanup_failures = _cleanup_workspace(workspace)
        if workspace_cleanup_failures:
            prior_cleanup_failures = (
                error.cleanup_failures if isinstance(error, DemoIssuanceError) else 0
            )
            code = (
                "DEMO_WORKSPACE_AND_OUTPUT_CLEANUP_FAILED"
                if prior_cleanup_failures
                else "DEMO_WORKSPACE_CLEANUP_FAILED"
            )
            raise DemoIssuanceError(
                code,
                cleanup_failures=prior_cleanup_failures + workspace_cleanup_failures,
            ) from error
        raise

    workspace_cleanup_failures = _cleanup_workspace(workspace)
    if workspace_cleanup_failures:
        output_cleanup_failures = _compensate_output(storage, output_key)
        code = (
            "DEMO_WORKSPACE_AND_OUTPUT_CLEANUP_FAILED"
            if output_cleanup_failures
            else "DEMO_WORKSPACE_CLEANUP_FAILED"
        )
        raise DemoIssuanceError(
            code,
            cleanup_failures=workspace_cleanup_failures + output_cleanup_failures,
        )

    try:
        committed = _commit_issuance_result(
            job_id=job.id,
            organization_id=job.organization_id,
            issuance_id=issuance.id,
            output_key=output_key,
            output_sha256=uploaded.actual_sha256,
            page_count=page_count,
        )
    except Exception as error:
        cleanup_failures = _compensate_output(storage, output_key)
        code = (
            "DEMO_RESULT_COMMIT_OUTPUT_CLEANUP_FAILED"
            if cleanup_failures
            else "DEMO_RESULT_COMMIT_FAILED"
        )
        raise DemoIssuanceError(code, cleanup_failures=cleanup_failures) from error
    if not committed:
        cleanup_failures = _compensate_output(storage, output_key)
        code = (
            "DEMO_JOB_CANCELLED_OUTPUT_CLEANUP_FAILED"
            if cleanup_failures
            else "DEMO_JOB_CANCELLED"
        )
        raise DemoIssuanceError(code, cleanup_failures=cleanup_failures)

    return IssuanceProcessingResult(
        organization_id=job.organization_id,
        job_id=job.id,
        issuance_id=issuance.id,
        input_sha256=downloaded.actual_sha256,
        output_sha256=uploaded.actual_sha256,
        output_object_key=output_key,
        algorithm_label=DEMO_ALGORITHM_LABEL,
        candidate_identifier=candidate_identifier,
        canonical_canvas=CANONICAL_CANVAS,
        pages_processed=page_count,
        processing_ms=max(0, round((time.monotonic() - started) * 1000)),
        limitations=LIMITATIONS,
        cleanup_failures=0,
    )


def _compensate_output(storage, output_key: str) -> int:
    try:
        storage.delete(key=output_key)
    except Exception:
        return 1
    return 0


def _cleanup_workspace(workspace) -> int:
    try:
        workspace.cleanup()
    except Exception:
        return 1
    return 0


def _validate_processing_job(job: Job) -> None:
    if not settings.SPLITBIND_DEMO_MODE:
        raise DemoIssuanceError("DEMO_MODE_DISABLED")
    if (
        job.kind != JobKind.ISSUANCE
        or job.status != JobStatus.PROCESSING
        or job.issuance_id is None
        or job.issuance.organization_id != job.organization_id
        or job.issuance.document.organization_id != job.organization_id
    ):
        raise DemoIssuanceError("DEMO_ISSUANCE_JOB_INVALID")


@transaction.atomic
def _cancel_before_work(job_id) -> bool:
    job = Job.objects.select_for_update().get(pk=job_id)
    if job.status != JobStatus.PROCESSING:
        raise DemoIssuanceError("DEMO_ISSUANCE_JOB_INVALID")
    if job.cancel_requested_at is None:
        return False
    transition_job(job, JobStatus.CANCELLED)
    job.save(update_fields=["status", "updated_at"])
    return True


@transaction.atomic
def _record_failed_job(job_id, code: str) -> None:
    job = Job.objects.select_for_update().get(pk=job_id)
    if job.status != JobStatus.PROCESSING:
        return
    transition_job(job, JobStatus.FAILED)
    job.safe_error_code = code
    job.save(update_fields=["status", "safe_error_code", "updated_at"])


def _load_fingerprint_key() -> bytes:
    encoded = os.environ.get(FINGERPRINT_KEY_ENV)
    if encoded is None or re.fullmatch(r"[0-9a-f]{64}", encoded) is None:
        raise DemoIssuanceError("DEMO_FINGERPRINT_KEY_INVALID")
    return bytes.fromhex(encoded)


def _select_frozen_candidate():
    candidates = load_v2_profiles()
    if not candidates:
        raise DemoIssuanceError("DEMO_FINGERPRINT_CANDIDATE_INVALID")
    candidate = candidates[0]
    identifier = candidate_identifier_v2(candidate).hex()
    if identifier != FROZEN_CANDIDATE_IDENTIFIER_HEX:
        raise DemoIssuanceError("DEMO_FINGERPRINT_CANDIDATE_INVALID")
    return candidate, identifier


def _build_issuance_pdf(
    source_pdf: bytes,
    *,
    issuance_id: uuid.UUID,
    fingerprint_key: bytes,
) -> tuple[bytes, int, str]:
    if len(source_pdf) > DEMO_MAX_PDF_BYTES:
        raise DemoIssuanceError("DEMO_PDF_FILE_LIMIT")
    if not source_pdf.startswith(b"%PDF-"):
        raise DemoIssuanceError("DEMO_PDF_INVALID")

    candidate, candidate_identifier = _select_frozen_candidate()
    try:
        input_pdf = pdfium.PdfDocument(source_pdf)
    except pdfium.PdfiumError as error:
        code = (
            "DEMO_PDF_ENCRYPTED"
            if error.err_code == pdfium.raw.FPDF_ERR_PASSWORD
            else "DEMO_PDF_INVALID"
        )
        raise DemoIssuanceError(code) from error
    except Exception as error:
        raise DemoIssuanceError("DEMO_PDF_INVALID") from error

    try:
        page_count = len(input_pdf)
        if not 1 <= page_count <= DEMO_MAX_PAGES:
            raise DemoIssuanceError("DEMO_PDF_PAGE_LIMIT")
        _validate_raster_budget(input_pdf)

        encoded_pages: list[tuple[bytes, int, int]] = []
        for page_index in range(page_count):
            source_page = input_pdf[page_index]
            try:
                bitmap = source_page.render(
                    scale=SOURCE_RENDER_SCALE,
                    fill_color=(255, 255, 255, 255),
                    draw_annots=True,
                )
                try:
                    rendered = np.asarray(bitmap.to_numpy(), dtype=np.uint8).copy()
                finally:
                    bitmap.close()
            finally:
                source_page.close()
            canvas = _canonicalize_page(rendered)
            embedded = embed_fingerprint_v2(
                canvas,
                FingerprintV2Context(
                    issuance_id=issuance_id,
                    fingerprint_key=fingerprint_key,
                    page_index=page_index,
                ),
                candidate,
            ).image
            encoded_pages.append(_encode_jpeg_page(embedded))

        return _serialize_image_only_pdf(encoded_pages), page_count, candidate_identifier
    finally:
        input_pdf.close()


def _validate_raster_budget(document: pdfium.PdfDocument) -> None:
    canvas_pixels = CANONICAL_CANVAS[0] * CANONICAL_CANVAS[1]
    cumulative_pixels = 0
    for page_index in range(len(document)):
        width, height = document.get_page_size(page_index)
        if not all(math.isfinite(value) and value > 0 for value in (width, height)):
            raise DemoIssuanceError("DEMO_PDF_INVALID")
        render_width = math.ceil(width * SOURCE_RENDER_SCALE)
        render_height = math.ceil(height * SOURCE_RENDER_SCALE)
        cumulative_pixels += max(render_width * render_height, canvas_pixels)
        if cumulative_pixels > DEMO_MAX_RASTER_PIXELS:
            raise DemoIssuanceError("DEMO_PDF_RASTER_LIMIT")


def _canonicalize_page(rendered: np.ndarray) -> np.ndarray:
    if rendered.ndim != 3 or rendered.shape[2] not in (3, 4):
        raise DemoIssuanceError("DEMO_PDF_RENDER_FAILED")
    if rendered.shape[2] == 4:
        rendered = rendered[:, :, :3]
    canvas_height, canvas_width = CANONICAL_CANVAS
    source_height, source_width = rendered.shape[:2]
    scale = min(canvas_width / source_width, canvas_height / source_height)
    target_width = max(1, min(canvas_width, round(source_width * scale)))
    target_height = max(1, min(canvas_height, round(source_height * scale)))
    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC
    fitted = cv2.resize(rendered, (target_width, target_height), interpolation=interpolation)
    canvas = np.full((canvas_height, canvas_width, 3), 255, dtype=np.uint8)
    left = (canvas_width - target_width) // 2
    top = (canvas_height - target_height) // 2
    canvas[top : top + target_height, left : left + target_width] = fitted
    return canvas


def _encode_jpeg_page(image: np.ndarray) -> tuple[bytes, int, int]:
    height, width = image.shape[:2]
    encoded_ok, encoded = cv2.imencode(
        ".jpg",
        image,
        [cv2.IMWRITE_JPEG_QUALITY, 95, cv2.IMWRITE_JPEG_OPTIMIZE, 0],
    )
    if not encoded_ok:
        raise DemoIssuanceError("DEMO_PDF_OUTPUT_FAILED")
    return encoded.tobytes(), width, height


def _serialize_image_only_pdf(encoded_pages: list[tuple[bytes, int, int]]) -> bytes:
    page_refs = [3 + page_index * 3 for page_index in range(len(encoded_pages))]
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        (
            b"<< /Type /Pages /Count "
            + str(len(page_refs)).encode("ascii")
            + b" /Kids ["
            + b" ".join(f"{page_ref} 0 R".encode("ascii") for page_ref in page_refs)
            + b"] >>"
        ),
    ]
    for page_index, (jpeg, width, height) in enumerate(encoded_pages):
        page_ref = page_refs[page_index]
        image_ref = page_ref + 1
        content_ref = page_ref + 2
        objects.extend(
            [
                (
                    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 "
                    + str(width).encode("ascii")
                    + b" "
                    + str(height).encode("ascii")
                    + b"] /Resources << /XObject << /Im0 "
                    + str(image_ref).encode("ascii")
                    + b" 0 R >> >> /Contents "
                    + str(content_ref).encode("ascii")
                    + b" 0 R >>"
                ),
                (
                    b"<< /Type /XObject /Subtype /Image /Width "
                    + str(width).encode("ascii")
                    + b" /Height "
                    + str(height).encode("ascii")
                    + b" /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length "
                    + str(len(jpeg)).encode("ascii")
                    + b" >>\nstream\n"
                    + jpeg
                    + b"\nendstream"
                ),
                _pdf_stream(
                    b"q\n"
                    + str(width).encode("ascii")
                    + b" 0 0 "
                    + str(height).encode("ascii")
                    + b" 0 0 cm\n/Im0 Do\nQ\n"
                ),
            ]
        )

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for object_number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{object_number} 0 obj\n".encode("ascii"))
        output.extend(body)
        output.extend(b"\nendobj\n")

    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.extend(
        b"trailer\n<< /Size "
        + str(len(objects) + 1).encode("ascii")
        + b" /Root 1 0 R >>\nstartxref\n"
        + str(xref_offset).encode("ascii")
        + b"\n%%EOF\n"
    )
    return bytes(output)


def _pdf_stream(contents: bytes) -> bytes:
    return (
        b"<< /Length "
        + str(len(contents)).encode("ascii")
        + b" >>\nstream\n"
        + contents
        + b"endstream"
    )


@transaction.atomic
def _commit_issuance_result(
    *,
    job_id,
    organization_id,
    issuance_id,
    output_key: str,
    output_sha256: str,
    page_count: int,
) -> bool:
    job = (
        Job.objects.select_for_update()
        .select_related("issuance__document")
        .get(pk=job_id)
    )
    if (
        job.organization_id != organization_id
        or job.kind != JobKind.ISSUANCE
        or job.status != JobStatus.PROCESSING
        or job.issuance_id != issuance_id
        or job.issuance.organization_id != organization_id
        or job.issuance.document.organization_id != organization_id
    ):
        raise DemoIssuanceError("DEMO_ISSUANCE_RESULT_INVALID")
    if job.cancel_requested_at is not None:
        transition_job(job, JobStatus.CANCELLED)
        job.save(update_fields=["status", "updated_at"])
        return False

    issuance = job.issuance
    document = issuance.document
    if issuance.output_object_key is not None or issuance.output_sha256 is not None:
        raise DemoIssuanceError("DEMO_ISSUANCE_RESULT_INVALID")
    issuance.output_object_key = output_key
    issuance.output_sha256 = output_sha256
    issuance.save(update_fields=["output_object_key", "output_sha256"])
    document.page_count = page_count
    document.save(update_fields=["page_count"])
    JobResultReceipt.objects.create(
        message_id=uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"splitbind-demo-issuance:{job.id}:{job.attempt}",
        ),
        organization_id=organization_id,
        job=job,
    )
    transition_job(job, JobStatus.SUCCEEDED)
    job.safe_error_code = None
    job.save(update_fields=["status", "safe_error_code", "updated_at"])
    return True
