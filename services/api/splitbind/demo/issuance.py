from __future__ import annotations

import math
import os
import re
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pypdfium2 as pdfium
from django.conf import settings
from django.db import transaction

from splitbind.demo.capabilities import DEMO_ALGORITHM_LABEL
from splitbind.demo.models import (
    DEMO_CANONICAL_CANVAS,
    DEMO_FROZEN_CANDIDATE_IDENTIFIER,
    DEMO_LIMITATIONS,
    DemoIssuanceResult,
    DemoOutputState,
    _allow_demo_result_write,
)
from splitbind.demo.results import IssuanceProcessingResult
from splitbind.documents.models import Document, Issuance
from splitbind.integrations.storage.base import StorageUnavailable, UploadRejected
from splitbind.jobs.models import Job, JobKind, JobResultReceipt, JobStatus
from splitbind.jobs.state import transition_job
from splitbind_ref.fingerprint_v2 import FingerprintV2Context, embed_fingerprint_v2
from splitbind_ref.fingerprint_v2_profile import candidate_identifier_v2, load_v2_profiles


DEMO_MAX_PDF_BYTES = 10 * 1024 * 1024
DEMO_MAX_PAGES = 5
DEMO_MAX_RASTER_PIXELS = 40_000_000
CANONICAL_CANVAS = DEMO_CANONICAL_CANVAS
SOURCE_RENDER_SCALE = 2.0
FINGERPRINT_KEY_ENV = "SPLITBIND_DEMO_FINGERPRINT_KEY_HEX"
FROZEN_CANDIDATE_IDENTIFIER_HEX = DEMO_FROZEN_CANDIDATE_IDENTIFIER
LIMITATIONS = DEMO_LIMITATIONS


class DemoIssuanceError(RuntimeError):
    def __init__(self, code: str, *, cleanup_failures: int = 0):
        super().__init__(code)
        self.code = code
        self.cleanup_failures = cleanup_failures


@dataclass(frozen=True, slots=True)
class _ProcessingClaim:
    job_id: uuid.UUID
    organization_id: uuid.UUID
    issuance_id: uuid.UUID
    document_id: uuid.UUID
    attempt: int
    source_object_key: str
    expected_source_sha256: str
    output_object_key: str
    owner_token: uuid.UUID


def process_issuance_job(*, job_id, storage) -> IssuanceProcessingResult:
    if not settings.SPLITBIND_DEMO_MODE:
        raise DemoIssuanceError("DEMO_MODE_DISABLED")
    started = time.monotonic()
    acquired = _acquire_processing_claim(job_id=job_id, owner_token=uuid.uuid4())
    if isinstance(acquired, IssuanceProcessingResult):
        return acquired
    if acquired is None:
        raise DemoIssuanceError("DEMO_JOB_CANCELLED")

    try:
        return _process_issuance_job(claim=acquired, storage=storage, started=started)
    except DemoIssuanceError as error:
        if error.code not in {
            "DEMO_JOB_CANCELLED",
            "DEMO_JOB_CANCELLED_OUTPUT_CLEANUP_FAILED",
        }:
            _record_failed_job(acquired, error)
        raise
    except Exception as error:
        wrapped = DemoIssuanceError("DEMO_ISSUANCE_PROCESSING_FAILED")
        _record_failed_job(acquired, wrapped)
        raise wrapped from error


@transaction.atomic
def _acquire_processing_claim(*, job_id, owner_token):
    job = _locked_job(job_id)
    issuance, document = _locked_issuance_document(job)
    _validate_locked_binding(job, issuance, document)

    if job.status == JobStatus.SUCCEEDED:
        return _load_replay_result(job, issuance, document)
    if job.status != JobStatus.PROCESSING:
        raise DemoIssuanceError("DEMO_ISSUANCE_JOB_INVALID")
    if job.cancel_requested_at is not None:
        transition_job(job, JobStatus.CANCELLED)
        job.save(update_fields=["status", "updated_at"])
        return None

    existing = (
        DemoIssuanceResult.objects.select_for_update().filter(job_id=job.id).first()
    )
    if existing is not None:
        raise DemoIssuanceError("DEMO_JOB_RESULT_OWNED")

    output_key = f"outputs/issuance/{job.organization_id}/{issuance.id}.pdf"
    evidence = DemoIssuanceResult(
        organization_id=job.organization_id,
        job=job,
        issuance=issuance,
        attempt=job.attempt,
        owner_token=owner_token,
        output_object_key=output_key,
    )
    with _allow_demo_result_write():
        evidence.save()
    return _ProcessingClaim(
        job_id=job.id,
        organization_id=job.organization_id,
        issuance_id=issuance.id,
        document_id=document.id,
        attempt=job.attempt,
        source_object_key=document.source_object_key,
        expected_source_sha256=document.expected_source_sha256,
        output_object_key=output_key,
        owner_token=owner_token,
    )


def _process_issuance_job(
    *,
    claim: _ProcessingClaim,
    storage,
    started: float,
) -> IssuanceProcessingResult:
    fingerprint_key = _load_fingerprint_key()
    workspace = tempfile.TemporaryDirectory(prefix=f"splitbind-demo-{claim.job_id}-")
    workspace_path = Path(workspace.name)

    try:
        try:
            downloaded = storage.download_bytes(
                key=claim.source_object_key,
                max_bytes=min(settings.MAX_PDF_BYTES, DEMO_MAX_PDF_BYTES),
                expected_sha256=claim.expected_source_sha256,
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
            issuance_id=claim.issuance_id,
            fingerprint_key=fingerprint_key,
        )
        output_path.write_bytes(output_bytes)
        if not _begin_output_upload(claim):
            raise DemoIssuanceError("DEMO_JOB_CANCELLED")
        try:
            with output_path.open("rb") as output_stream:
                uploaded = storage.upload_bytes(
                    key=claim.output_object_key,
                    content_type="application/pdf",
                    chunks=iter(lambda: output_stream.read(64 * 1024), b""),
                    max_bytes=min(settings.MAX_PDF_BYTES, DEMO_MAX_PDF_BYTES),
                )
        except Exception as error:
            cleanup_failures, code = _compensate_owned_output(
                storage=storage,
                claim=claim,
                cleaned_code="DEMO_OUTPUT_STORAGE_FAILED",
                cleanup_failed_code="DEMO_OUTPUT_STORAGE_CLEANUP_FAILED",
            )
            raise DemoIssuanceError(code, cleanup_failures=cleanup_failures) from error
    except Exception as error:
        workspace_cleanup_failures = _cleanup_workspace(workspace)
        if workspace_cleanup_failures:
            prior_cleanup_failures = (
                error.cleanup_failures if isinstance(error, DemoIssuanceError) else 0
            )
            code = "DEMO_WORKSPACE_CLEANUP_FAILED"
            if prior_cleanup_failures:
                code = "DEMO_WORKSPACE_AND_OUTPUT_CLEANUP_FAILED"
            raise DemoIssuanceError(
                code,
                cleanup_failures=prior_cleanup_failures + workspace_cleanup_failures,
            ) from error
        raise

    workspace_cleanup_failures = _cleanup_workspace(workspace)
    if workspace_cleanup_failures:
        cleanup_failures, code = _compensate_owned_output(
            storage=storage,
            claim=claim,
            cleaned_code="DEMO_WORKSPACE_CLEANUP_FAILED",
            cleanup_failed_code="DEMO_WORKSPACE_AND_OUTPUT_CLEANUP_FAILED",
            prior_cleanup_failures=workspace_cleanup_failures,
        )
        raise DemoIssuanceError(
            code,
            cleanup_failures=cleanup_failures,
        )

    processing_ms = max(0, round((time.monotonic() - started) * 1000))
    try:
        committed = _commit_issuance_result(
            claim=claim,
            input_sha256=downloaded.actual_sha256,
            output_sha256=uploaded.actual_sha256,
            page_count=page_count,
            candidate_identifier=candidate_identifier,
            processing_ms=processing_ms,
        )
    except Exception as error:
        cleanup_failures, code = _compensate_owned_output(
            storage=storage,
            claim=claim,
            cleaned_code="DEMO_RESULT_COMMIT_FAILED",
            cleanup_failed_code="DEMO_RESULT_COMMIT_OUTPUT_CLEANUP_FAILED",
        )
        raise DemoIssuanceError(code, cleanup_failures=cleanup_failures) from error
    if committed is None:
        cleanup_failures, code = _compensate_owned_output(
            storage=storage,
            claim=claim,
            cleaned_code="DEMO_JOB_CANCELLED",
            cleanup_failed_code="DEMO_JOB_CANCELLED_OUTPUT_CLEANUP_FAILED",
        )
        raise DemoIssuanceError(code, cleanup_failures=cleanup_failures)
    return committed


def _compensate_owned_output(
    *,
    storage,
    claim: _ProcessingClaim,
    cleaned_code: str,
    cleanup_failed_code: str,
    prior_cleanup_failures: int = 0,
) -> tuple[int, str]:
    _authorize_output_cleanup(claim)
    try:
        storage.delete(key=claim.output_object_key)
    except Exception:
        cleanup_failures = prior_cleanup_failures + 1
        _persist_output_cleanup(
            claim,
            output_state=DemoOutputState.CLEANUP_REQUIRED,
            safe_error_code=cleanup_failed_code,
            cleanup_failures=cleanup_failures,
        )
        return cleanup_failures, cleanup_failed_code
    _persist_output_cleanup(
        claim,
        output_state=DemoOutputState.CLEANED,
        safe_error_code=cleaned_code,
        cleanup_failures=prior_cleanup_failures,
    )
    return prior_cleanup_failures, cleaned_code


def _cleanup_workspace(workspace) -> int:
    try:
        workspace.cleanup()
    except Exception:
        return 1
    return 0


@transaction.atomic
def _begin_output_upload(claim: _ProcessingClaim) -> bool:
    job = _locked_job(claim.job_id)
    issuance, document = _locked_issuance_document(job)
    _validate_claim_binding(claim, job, issuance, document)
    evidence = _locked_evidence(claim)
    if job.status != JobStatus.PROCESSING or evidence.output_state != DemoOutputState.RESERVED:
        raise DemoIssuanceError("DEMO_OUTPUT_OWNERSHIP_INVALID")
    if job.cancel_requested_at is not None:
        transition_job(job, JobStatus.CANCELLED)
        job.save(update_fields=["status", "updated_at"])
        evidence.output_state = DemoOutputState.CLEANED
        with _allow_demo_result_write():
            evidence.save(update_fields=["output_state", "updated_at"])
        return False
    evidence.output_state = DemoOutputState.UPLOADING
    with _allow_demo_result_write():
        evidence.save(update_fields=["output_state", "updated_at"])
    return True


@transaction.atomic
def _record_failed_job(claim: _ProcessingClaim, error: DemoIssuanceError) -> None:
    job = _locked_job(claim.job_id)
    evidence = _locked_evidence(claim)
    if job.status != JobStatus.PROCESSING:
        return
    transition_job(job, JobStatus.FAILED)
    job.safe_error_code = error.code
    job.save(update_fields=["status", "safe_error_code", "updated_at"])
    if evidence.output_state == DemoOutputState.RESERVED:
        evidence.output_state = DemoOutputState.CLEANED
    elif evidence.output_state == DemoOutputState.UPLOADING:
        evidence.output_state = DemoOutputState.CLEANUP_REQUIRED
    evidence.safe_error_code = error.code
    evidence.cleanup_failures = error.cleanup_failures
    with _allow_demo_result_write():
        evidence.save(
            update_fields=[
                "output_state",
                "safe_error_code",
                "cleanup_failures",
                "updated_at",
            ]
        )


@transaction.atomic
def _authorize_output_cleanup(claim: _ProcessingClaim) -> None:
    job = _locked_job(claim.job_id)
    issuance, document = _locked_issuance_document(job)
    _validate_claim_binding(claim, job, issuance, document)
    evidence = _locked_evidence(claim)
    if (
        evidence.output_state
        not in {DemoOutputState.UPLOADING, DemoOutputState.CLEANUP_REQUIRED}
        or issuance.output_object_key is not None
        or job.status == JobStatus.SUCCEEDED
    ):
        raise DemoIssuanceError("DEMO_OUTPUT_OWNERSHIP_INVALID")


@transaction.atomic
def _persist_output_cleanup(
    claim: _ProcessingClaim,
    *,
    output_state: str,
    safe_error_code: str,
    cleanup_failures: int,
) -> None:
    job = _locked_job(claim.job_id)
    issuance, document = _locked_issuance_document(job)
    _validate_claim_binding(claim, job, issuance, document)
    evidence = _locked_evidence(claim)
    if evidence.output_state not in {
        DemoOutputState.UPLOADING,
        DemoOutputState.CLEANUP_REQUIRED,
    }:
        raise DemoIssuanceError("DEMO_OUTPUT_OWNERSHIP_INVALID")
    evidence.output_state = output_state
    evidence.safe_error_code = safe_error_code
    evidence.cleanup_failures = cleanup_failures
    with _allow_demo_result_write():
        evidence.save(
            update_fields=[
                "output_state",
                "safe_error_code",
                "cleanup_failures",
                "updated_at",
            ]
        )
    if job.status == JobStatus.CANCELLED:
        job.safe_error_code = safe_error_code if cleanup_failures else None
        job.save(update_fields=["safe_error_code", "updated_at"])


def _locked_job(job_id) -> Job:
    return (
        Job.objects.filter(issuance__isnull=False)
        .select_for_update(of=("self",))
        .get(pk=job_id)
    )


def _locked_issuance_document(job: Job) -> tuple[Issuance, Document]:
    issuance = Issuance.objects.select_for_update().get(pk=job.issuance_id)
    document = Document.objects.select_for_update().get(pk=issuance.document_id)
    return issuance, document


def _validate_locked_binding(job: Job, issuance: Issuance, document: Document) -> None:
    if (
        job.kind != JobKind.ISSUANCE
        or job.issuance_id != issuance.id
        or issuance.organization_id != job.organization_id
        or document.id != issuance.document_id
        or document.organization_id != job.organization_id
    ):
        raise DemoIssuanceError("DEMO_ISSUANCE_JOB_INVALID")


def _validate_claim_binding(
    claim: _ProcessingClaim,
    job: Job,
    issuance: Issuance,
    document: Document,
) -> None:
    _validate_locked_binding(job, issuance, document)
    if (
        job.id != claim.job_id
        or job.organization_id != claim.organization_id
        or issuance.id != claim.issuance_id
        or document.id != claim.document_id
        or job.attempt != claim.attempt
    ):
        raise DemoIssuanceError("DEMO_OUTPUT_OWNERSHIP_INVALID")


def _locked_evidence(claim: _ProcessingClaim) -> DemoIssuanceResult:
    evidence = DemoIssuanceResult.objects.select_for_update().get(job_id=claim.job_id)
    if (
        evidence.organization_id != claim.organization_id
        or evidence.issuance_id != claim.issuance_id
        or evidence.attempt != claim.attempt
        or evidence.owner_token != claim.owner_token
        or evidence.output_object_key != claim.output_object_key
    ):
        raise DemoIssuanceError("DEMO_OUTPUT_OWNERSHIP_INVALID")
    return evidence


def _receipt_id(job: Job) -> uuid.UUID:
    return uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"splitbind-demo-issuance:{job.id}:{job.attempt}",
    )


def _load_replay_result(
    job: Job,
    issuance: Issuance,
    document: Document,
) -> IssuanceProcessingResult:
    evidence = DemoIssuanceResult.objects.select_for_update().get(job_id=job.id)
    receipt_exists = JobResultReceipt.objects.select_for_update().filter(
        message_id=_receipt_id(job),
        organization_id=job.organization_id,
        job_id=job.id,
    ).exists()
    if (
        evidence.output_state != DemoOutputState.COMMITTED
        or evidence.organization_id != job.organization_id
        or evidence.issuance_id != issuance.id
        or evidence.attempt != job.attempt
        or issuance.output_object_key != evidence.output_object_key
        or issuance.output_sha256 != evidence.output_sha256
        or document.page_count != evidence.page_count
        or not receipt_exists
    ):
        raise DemoIssuanceError("DEMO_ISSUANCE_RESULT_INVALID")
    evidence.full_clean()
    return _result_from_evidence(evidence)


def _result_from_evidence(evidence: DemoIssuanceResult) -> IssuanceProcessingResult:
    return IssuanceProcessingResult(
        organization_id=evidence.organization_id,
        job_id=evidence.job_id,
        issuance_id=evidence.issuance_id,
        input_sha256=evidence.input_sha256,
        output_sha256=evidence.output_sha256,
        output_object_key=evidence.output_object_key,
        algorithm_label=evidence.algorithm_label,
        candidate_identifier=evidence.candidate_identifier,
        canonical_canvas=(evidence.canvas_height, evidence.canvas_width),
        pages_processed=evidence.page_count,
        processing_ms=evidence.processing_ms,
        limitations=tuple(evidence.limitations),
        cleanup_failures=evidence.cleanup_failures,
    )


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
    claim: _ProcessingClaim,
    input_sha256: str,
    output_sha256: str,
    page_count: int,
    candidate_identifier: str,
    processing_ms: int,
) -> IssuanceProcessingResult | None:
    job = _locked_job(claim.job_id)
    issuance, document = _locked_issuance_document(job)
    _validate_claim_binding(claim, job, issuance, document)
    evidence = _locked_evidence(claim)
    if job.status != JobStatus.PROCESSING:
        raise DemoIssuanceError("DEMO_ISSUANCE_RESULT_INVALID")
    if job.cancel_requested_at is not None:
        transition_job(job, JobStatus.CANCELLED)
        job.save(update_fields=["status", "updated_at"])
        return None

    if (
        evidence.output_state != DemoOutputState.UPLOADING
        or issuance.output_object_key is not None
        or issuance.output_sha256 is not None
    ):
        raise DemoIssuanceError("DEMO_ISSUANCE_RESULT_INVALID")
    issuance.output_object_key = claim.output_object_key
    issuance.output_sha256 = output_sha256
    issuance.save(update_fields=["output_object_key", "output_sha256"])
    document.page_count = page_count
    document.save(update_fields=["page_count"])
    JobResultReceipt.objects.create(
        message_id=_receipt_id(job),
        organization_id=claim.organization_id,
        job=job,
    )
    evidence.output_state = DemoOutputState.COMMITTED
    evidence.algorithm_label = DEMO_ALGORITHM_LABEL
    evidence.candidate_identifier = candidate_identifier
    evidence.canvas_height, evidence.canvas_width = CANONICAL_CANVAS
    evidence.input_sha256 = input_sha256
    evidence.output_sha256 = output_sha256
    evidence.page_count = page_count
    evidence.processing_ms = processing_ms
    evidence.limitations = list(LIMITATIONS)
    evidence.cleanup_failures = 0
    evidence.safe_error_code = None
    with _allow_demo_result_write():
        evidence.save(
            update_fields=[
                "output_state",
                "algorithm_label",
                "candidate_identifier",
                "canvas_height",
                "canvas_width",
                "input_sha256",
                "output_sha256",
                "page_count",
                "processing_ms",
                "limitations",
                "cleanup_failures",
                "safe_error_code",
                "updated_at",
            ]
        )
    transition_job(job, JobStatus.SUCCEEDED)
    job.safe_error_code = None
    job.save(update_fields=["status", "safe_error_code", "updated_at"])
    return _result_from_evidence(evidence)
