from __future__ import annotations

import json
from io import BytesIO
import math
import struct
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pypdfium2 as pdfium
from pypdf import PdfReader
from pypdf.errors import PyPdfError
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from splitbind.demo.capabilities import DEMO_ALGORITHM_LABEL
from splitbind.demo.issuance import DemoIssuanceError as DemoIssuanceProcessingError
from splitbind.demo.issuance import _canonicalize_page, _load_fingerprint_key
from splitbind.demo.issuance import _receipt_id as _issuance_receipt_id
from splitbind.demo.issuance import accepted_decode_candidates
from splitbind.access.models import SigningKey
from splitbind.demo.models import (
    DEMO_CANONICAL_CANVAS,
    DEMO_VERIFICATION_LIMITATIONS,
    DemoIssuanceResult,
    DemoOutputState,
    DemoVerificationResult,
    DemoVerificationState,
    _allow_demo_result_write,
)
from splitbind.demo.results import VerificationProcessingResult
from splitbind.documents.manifests import verify_stored_manifest
from splitbind.documents.models import Document, Issuance, Manifest, Verification, VerificationStatus
from splitbind.integrations.storage.base import (
    StorageUnavailable,
    UploadRejected,
    validate_promoted_key,
)
from splitbind.jobs.models import Job, JobKind, JobResultReceipt, JobStatus
from splitbind.jobs.state import transition_job
from splitbind.release.mode import integrity_release_enabled
from splitbind.uploads.models import PromotionStatus, UploadPurpose, UploadRequest
from splitbind_ref.fingerprint_v2 import DecodeV2Decision, decode_fingerprint_v2
from splitbind_ref.frame_restore import restore_frame


PAGE_INDEX_HYPOTHESES = 5
PDF_RENDER_SCALE = 2.0
_LEGACY_CANONICAL_PAGE_CONTENT = b"q\n1152 0 0 2304 0 0 cm\n/Im0 Do\nQ\n"
_UNKNOWN_PAGE_MIN_CONSISTENT_DECODES = 1
_BASE_LIMITATIONS = DEMO_VERIFICATION_LIMITATIONS
INTEGRITY_ALGORITHM_LABEL = "integrity_release_v1"
TRANSFORMED_ATTRIBUTION_UNAVAILABLE = "fingerprint.transformed_attribution_unavailable"
FINGERPRINT_BELOW_RELEASE_GATE = "fingerprint.recall_below_release_gate"


class DemoVerificationError(RuntimeError):
    def __init__(self, code: str, *, cleanup_failures: int = 0):
        super().__init__(code)
        self.code = code
        self.cleanup_failures = cleanup_failures


@dataclass(frozen=True, slots=True)
class _ProcessingClaim:
    job_id: uuid.UUID
    organization_id: uuid.UUID
    verification_id: uuid.UUID
    upload_id: uuid.UUID
    attempt: int
    input_object_key: str
    expected_input_sha256: str
    owner_token: uuid.UUID


@dataclass(frozen=True, slots=True)
class _DecodeSummary:
    issuance_id: uuid.UUID | None
    confidence: float
    valid_votes: int
    status: str


@dataclass(frozen=True, slots=True)
class _SourceResolution:
    status: str
    recovered_issuance_id: uuid.UUID | None
    exact_file_hash_match: bool
    manifest_signature_valid: bool | None
    limitations: tuple[str, ...]


def process_verification_job(
    *, job_id, storage, owner_token: uuid.UUID | None = None
) -> VerificationProcessingResult:
    integrity_mode = integrity_release_enabled(
        getattr(settings, "SPLITBIND_RELEASE_MODE", None)
    )
    if not settings.SPLITBIND_DEMO_MODE and not integrity_mode:
        raise DemoVerificationError("DEMO_MODE_DISABLED")
    started = time.monotonic()
    acquired = _acquire_processing_claim(
        job_id=job_id,
        owner_token=owner_token or uuid.uuid4(),
    )
    if isinstance(acquired, VerificationProcessingResult):
        return acquired
    if acquired is None:
        raise DemoVerificationError("DEMO_JOB_CANCELLED")

    try:
        fingerprint_enabled = bool(
            getattr(settings, "SPLITBIND_FINGERPRINT_ENABLED", False)
        )
        fingerprint_key = None
        candidates = ()
        if not integrity_mode or fingerprint_enabled:
            try:
                fingerprint_key = _load_fingerprint_key()
                candidates = accepted_decode_candidates()
            except DemoIssuanceProcessingError as error:
                raise DemoVerificationError(error.code) from error
        if _cancel_before_work(acquired):
            raise DemoVerificationError("DEMO_JOB_CANCELLED")
        try:
            downloaded = storage.download_bytes(
                key=acquired.input_object_key,
                max_bytes=settings.MAX_PDF_BYTES,
                expected_sha256=acquired.expected_input_sha256,
            )
        except UploadRejected as error:
            code = (
                "DEMO_INPUT_CHECKSUM_MISMATCH"
                if str(error) == "STORAGE_CHECKSUM_MISMATCH"
                else "DEMO_INPUT_FILE_LIMIT"
                if str(error) == "STORAGE_BYTE_LIMIT"
                else "DEMO_INPUT_STORAGE_REJECTED"
            )
            raise DemoVerificationError(code) from error
        except StorageUnavailable as error:
            raise DemoVerificationError("DEMO_INPUT_STORAGE_FAILED") from error

        if _cancel_before_work(acquired):
            raise DemoVerificationError("DEMO_JOB_CANCELLED")

        workspace = tempfile.TemporaryDirectory(
            prefix=f"splitbind-demo-verify-{acquired.job_id}-"
        )
        workspace_path = Path(workspace.name)
        try:
            source_path = workspace_path / "suspect.bin"
            source_path.write_bytes(downloaded.data)
            source_bytes = source_path.read_bytes()
            if integrity_mode and not fingerprint_enabled:
                pages_analyzed = _inspect_integrity_content(source_bytes)
                decode = _DecodeSummary(None, 0.0, 0, "payload_not_detected")
            else:
                decode, pages_analyzed = _decode_content(
                    source_bytes,
                    fingerprint_key=fingerprint_key,
                    candidates=candidates,
                )
        except Exception as error:
            cleanup_failures = _cleanup_workspace(workspace)
            if cleanup_failures:
                raise DemoVerificationError(
                    "DEMO_WORKSPACE_CLEANUP_FAILED",
                    cleanup_failures=cleanup_failures,
                ) from error
            raise
        cleanup_failures = _cleanup_workspace(workspace)
        if cleanup_failures:
            raise DemoVerificationError(
                "DEMO_WORKSPACE_CLEANUP_FAILED",
                cleanup_failures=cleanup_failures,
            )

        processing_ms = max(0, round((time.monotonic() - started) * 1000))
        try:
            committed = _commit_verification_result(
                claim=acquired,
                input_sha256=downloaded.actual_sha256,
                decode=decode,
                pages_analyzed=pages_analyzed,
                processing_ms=processing_ms,
                exact_only=integrity_mode and not fingerprint_enabled,
            )
        except DemoVerificationError:
            raise
        except Exception as error:
            raise DemoVerificationError("DEMO_RESULT_COMMIT_FAILED") from error
        if committed is None:
            raise DemoVerificationError("DEMO_JOB_CANCELLED")
        return committed
    except DemoVerificationError as error:
        if error.code != "DEMO_JOB_CANCELLED":
            _record_failed_job(acquired, error, started=started)
        raise
    except Exception as error:
        wrapped = DemoVerificationError("DEMO_VERIFICATION_PROCESSING_FAILED")
        _record_failed_job(acquired, wrapped, started=started)
        raise wrapped from error


@transaction.atomic
def _acquire_processing_claim(*, job_id, owner_token):
    job = _locked_job(job_id)
    verification, upload = _locked_verification_upload(job)
    _validate_locked_binding(job, verification, upload)

    if job.status == JobStatus.SUCCEEDED:
        return _load_replay_result(job, verification, upload)
    if job.status != JobStatus.PROCESSING:
        raise DemoVerificationError("DEMO_VERIFICATION_JOB_INVALID")
    existing = (
        DemoVerificationResult.objects.select_for_update().filter(job_id=job.id).first()
    )
    if existing is not None:
        if (
            existing.owner_token != owner_token
            or existing.result_state != DemoVerificationState.RESERVED
            or existing.organization_id != job.organization_id
            or existing.verification_id != verification.id
            or existing.attempt != job.attempt
        ):
            raise DemoVerificationError("DEMO_JOB_RESULT_OWNED")
        return _ProcessingClaim(
            job_id=job.id,
            organization_id=job.organization_id,
            verification_id=verification.id,
            upload_id=upload.id,
            attempt=job.attempt,
            input_object_key=upload.promotion_target_key,
            expected_input_sha256=upload.expected_sha256,
            owner_token=owner_token,
        )

    evidence = DemoVerificationResult(
        organization_id=job.organization_id,
        job=job,
        verification=verification,
        attempt=job.attempt,
        owner_token=owner_token,
    )
    with _allow_demo_result_write():
        evidence.save()

    claim = _ProcessingClaim(
        job_id=job.id,
        organization_id=job.organization_id,
        verification_id=verification.id,
        upload_id=upload.id,
        attempt=job.attempt,
        input_object_key=upload.promotion_target_key,
        expected_input_sha256=upload.expected_sha256,
        owner_token=owner_token,
    )
    if job.cancel_requested_at is not None:
        _cancel_locked(job, evidence)
        return None
    return claim


def _decode_content(
    source: bytes, *, fingerprint_key: bytes, candidates
) -> tuple[_DecodeSummary, int]:
    if len(source) > settings.MAX_PDF_BYTES:
        raise DemoVerificationError("DEMO_INPUT_FILE_LIMIT")
    if source.startswith(b"%PDF-"):
        return _decode_pdf(source, fingerprint_key=fingerprint_key, candidates=candidates)
    if source.startswith(b"\x89PNG\r\n\x1a\n"):
        return _decode_png(source, fingerprint_key=fingerprint_key, candidates=candidates)
    if source.startswith(b"\xff\xd8\xff"):
        return _decode_jpeg(source, fingerprint_key=fingerprint_key, candidates=candidates)
    raise DemoVerificationError("DEMO_INPUT_FORMAT_INVALID")


def _inspect_integrity_content(source: bytes) -> int:
    """Validate a bounded input without executing hidden-fingerprint recovery."""
    if len(source) > settings.MAX_PDF_BYTES:
        raise DemoVerificationError("DEMO_INPUT_FILE_LIMIT")
    if source.startswith(b"%PDF-"):
        try:
            document = pdfium.PdfDocument(source)
        except pdfium.PdfiumError as error:
            code = (
                "DEMO_PDF_ENCRYPTED"
                if error.err_code == pdfium.raw.FPDF_ERR_PASSWORD
                else "DEMO_PDF_INVALID"
            )
            raise DemoVerificationError(code) from error
        except Exception as error:
            raise DemoVerificationError("DEMO_PDF_INVALID") from error
        try:
            document.init_forms()
            page_count = len(document)
            if not 1 <= page_count <= settings.MAX_PDF_PAGES:
                raise DemoVerificationError("DEMO_PDF_PAGE_LIMIT")
            _page_units, render_scales = _pdf_page_metadata(source, page_count)
            _validate_pdf_raster_budget(document, render_scales)
            return page_count
        finally:
            document.close()
    if source.startswith(b"\x89PNG\r\n\x1a\n") or source.startswith(b"\xff\xd8\xff"):
        image = cv2.imdecode(np.frombuffer(source, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        if image is None or image.ndim not in (2, 3):
            raise DemoVerificationError("DEMO_IMAGE_INVALID")
        _validate_image_dimensions(width=image.shape[1], height=image.shape[0])
        return 1
    raise DemoVerificationError("DEMO_INPUT_FORMAT_INVALID")


def _decode_pdf(source: bytes, *, fingerprint_key: bytes, candidates) -> tuple[_DecodeSummary, int]:
    try:
        document = pdfium.PdfDocument(source)
    except pdfium.PdfiumError as error:
        code = (
            "DEMO_PDF_ENCRYPTED"
            if error.err_code == pdfium.raw.FPDF_ERR_PASSWORD
            else "DEMO_PDF_INVALID"
        )
        raise DemoVerificationError(code) from error
    except Exception as error:
        raise DemoVerificationError("DEMO_PDF_INVALID") from error

    try:
        document.init_forms()
        page_count = len(document)
        if not 1 <= page_count <= settings.MAX_PDF_PAGES:
            raise DemoVerificationError("DEMO_PDF_PAGE_LIMIT")
        _page_units, render_scales = _pdf_page_metadata(source, page_count)
        _validate_pdf_raster_budget(document, render_scales)
        decisions: list[DecodeV2Decision] = []
        for page_index in range(page_count):
            page = document[page_index]
            try:
                bitmap = page.render(
                    scale=render_scales[page_index],
                    fill_color=(255, 255, 255, 255),
                    draw_annots=True,
                )
                try:
                    raster = np.asarray(bitmap.to_numpy(), dtype=np.uint8).copy()
                finally:
                    bitmap.close()
            finally:
                page.close()
            if raster.ndim != 3 or raster.shape[2] not in (3, 4):
                raise DemoVerificationError("DEMO_PDF_RENDER_FAILED")
            if raster.shape[2] == 4:
                raster = raster[:, :, :3]
            canvas = np.ascontiguousarray(_canonicalize_page(raster).canvas)
            decisions.append(
                _first_conclusive_decision(
                    canvas,
                    fingerprint_key=fingerprint_key,
                    page_index=page_index,
                    candidates=candidates,
                )
            )
        return _aggregate_decisions(decisions), page_count
    finally:
        document.close()


def _decode_png(source: bytes, *, fingerprint_key: bytes, candidates) -> tuple[_DecodeSummary, int]:
    if (
        len(source) < 33
        or source[8:12] != b"\x00\x00\x00\r"
        or source[12:16] != b"IHDR"
    ):
        raise DemoVerificationError("DEMO_IMAGE_INVALID")
    width, height = struct.unpack(">II", source[16:24])
    _validate_image_dimensions(width=width, height=height)
    return _decode_image(
        source,
        width=width,
        height=height,
        fingerprint_key=fingerprint_key,
        candidates=candidates,
    )


def _decode_jpeg(source: bytes, *, fingerprint_key: bytes, candidates) -> tuple[_DecodeSummary, int]:
    width, height = _jpeg_dimensions(source)
    _validate_image_dimensions(width=width, height=height)
    return _decode_image(
        source,
        width=width,
        height=height,
        fingerprint_key=fingerprint_key,
        candidates=candidates,
    )


def _geometry_hypotheses(raster: np.ndarray) -> list[np.ndarray]:
    hypotheses = [np.ascontiguousarray(_canonicalize_page(raster).canvas)]
    restored = restore_frame(raster, DEMO_CANONICAL_CANVAS)
    if restored is not None:
        hypotheses.append(np.ascontiguousarray(restored.image))
    return hypotheses


def _first_conclusive_decision(canvas, *, fingerprint_key, page_index, candidates):
    """Try each profile in turn and stop as soon as one reaches the payload.

    The decoder aligns geometry once per profile, so handing it every profile at
    once makes a current artifact pay for the superseded ones as well. Ordering
    the attempts keeps the common case at its original cost.
    """

    fallback = None
    for candidate in candidates:
        decision = decode_fingerprint_v2(
            canvas,
            fingerprint_key,
            page_index,
            DEMO_CANONICAL_CANVAS,
            (candidate,),
        )
        if decision.status in ("decoded", "partial_payload_evidence"):
            return decision
        if fallback is None:
            fallback = decision
    return fallback


def _decode_image(
    source: bytes,
    *,
    width: int,
    height: int,
    fingerprint_key: bytes,
    candidates,
) -> tuple[_DecodeSummary, int]:
    raster = cv2.imdecode(np.frombuffer(source, dtype=np.uint8), cv2.IMREAD_COLOR)
    if (
        raster is None
        or raster.dtype != np.uint8
        or raster.ndim != 3
        or raster.shape != (height, width, 3)
    ):
        raise DemoVerificationError("DEMO_IMAGE_INVALID")
    fallback = None
    for page in _geometry_hypotheses(raster):
        decisions = [
            _first_conclusive_decision(
                page,
                fingerprint_key=fingerprint_key,
                page_index=page_index,
                candidates=candidates,
            )
            for page_index in range(PAGE_INDEX_HYPOTHESES)
        ]
        summary = _aggregate_unknown_page_decisions(decisions)
        if summary.status in ("decoded", "partial_payload_evidence"):
            return summary, 1
        if fallback is None:
            fallback = summary
    return fallback, 1


def _jpeg_dimensions(source: bytes) -> tuple[int, int]:
    start_of_frame = {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
    offset = 2
    while offset < len(source):
        if source[offset] != 0xFF:
            raise DemoVerificationError("DEMO_IMAGE_INVALID")
        while offset < len(source) and source[offset] == 0xFF:
            offset += 1
        if offset >= len(source):
            break
        marker = source[offset]
        offset += 1
        if marker in {0x00, 0xD8}:
            continue
        if marker in {0xD9, 0xDA}:
            break
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:
            continue
        if offset + 2 > len(source):
            break
        segment_length = struct.unpack(">H", source[offset : offset + 2])[0]
        if segment_length < 2 or offset + segment_length > len(source):
            break
        if marker in start_of_frame:
            if segment_length < 8:
                break
            height, width = struct.unpack(">HH", source[offset + 3 : offset + 7])
            return width, height
        offset += segment_length
    raise DemoVerificationError("DEMO_IMAGE_INVALID")


def _validate_image_dimensions(*, width: int, height: int) -> None:
    if width <= 0 or height <= 0:
        raise DemoVerificationError("DEMO_IMAGE_INVALID")
    if width * height > settings.MAX_IMAGE_PIXELS:
        raise DemoVerificationError("DEMO_INPUT_RASTER_LIMIT")


def _pdf_page_metadata(
    source: bytes, page_count: int
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    try:
        with BytesIO(source) as stream:
            reader = PdfReader(stream, strict=True)
            if reader.is_encrypted or len(reader.pages) != page_count:
                raise DemoVerificationError("DEMO_PDF_INVALID")
            units = tuple(float(page.user_unit) for page in reader.pages)
            if any(not math.isfinite(unit) or not 0 < unit <= 75_000 for unit in units):
                raise DemoVerificationError("DEMO_PDF_INVALID")
            render_scales = tuple(
                1.0 if _is_legacy_canonical_page(page, unit) else PDF_RENDER_SCALE * unit
                for page, unit in zip(reader.pages, units)
            )
    except DemoVerificationError:
        raise
    except (PyPdfError, TypeError, ValueError, OverflowError, KeyError) as error:
        raise DemoVerificationError("DEMO_PDF_INVALID") from error
    return units, render_scales


def _is_legacy_canonical_page(page, user_unit: float) -> bool:
    if user_unit != 1.0 or page.rotation != 0:
        return False
    if set(page) != {"/Type", "/Parent", "/MediaBox", "/Resources", "/Contents"}:
        return False
    if page.get("/Type") != "/Page":
        return False
    expected_box = (0.0, 0.0, 1152.0, 2304.0)
    if tuple(float(value) for value in page.mediabox) != expected_box:
        return False
    if tuple(float(value) for value in page.cropbox) != expected_box:
        return False
    contents = page.get_contents()
    if contents is None or contents.get_data() != _LEGACY_CANONICAL_PAGE_CONTENT:
        return False
    resources = page.get("/Resources")
    if resources is None:
        return False
    resources = resources.get_object()
    if set(resources) != {"/XObject"}:
        return False
    xobjects = resources.get("/XObject")
    if xobjects is None:
        return False
    xobjects = xobjects.get_object()
    if set(xobjects) != {"/Im0"}:
        return False
    image = xobjects["/Im0"].get_object()
    if set(image) != {
        "/Type",
        "/Subtype",
        "/Width",
        "/Height",
        "/ColorSpace",
        "/BitsPerComponent",
        "/Filter",
    }:
        return False
    return (
        image.get("/Type") == "/XObject"
        and image.get("/Subtype") == "/Image"
        and image.get("/Filter") == "/DCTDecode"
        and int(image.get("/Width", 0)) == 1152
        and int(image.get("/Height", 0)) == 2304
        and image.get("/ColorSpace") == "/DeviceRGB"
        and int(image.get("/BitsPerComponent", 0)) == 8
    )


def _validate_pdf_raster_budget(
    document: pdfium.PdfDocument, render_scales: tuple[float, ...]
) -> None:
    cumulative_pixels = 0
    for page_index in range(len(document)):
        width, height = document.get_page_size(page_index)
        if not all(math.isfinite(value) and value > 0 for value in (width, height)):
            raise DemoVerificationError("DEMO_PDF_INVALID")
        render_width = math.ceil(width * render_scales[page_index])
        render_height = math.ceil(height * render_scales[page_index])
        cumulative_pixels += render_width * render_height
        if cumulative_pixels > settings.MAX_DOCUMENT_RASTER_PIXELS:
            raise DemoVerificationError("DEMO_INPUT_RASTER_LIMIT")


def _aggregate_decisions(decisions: list[DecodeV2Decision]) -> _DecodeSummary:
    decoded = {decision.issuance_id for decision in decisions if decision.status == "decoded"}
    confidence = max((decision.confidence for decision in decisions), default=0.0)
    valid_votes = sum(decision.valid_votes for decision in decisions)
    if any(
        decision.status == "partial_payload_evidence" for decision in decisions
    ) or len(decoded) > 1:
        return _DecodeSummary(
            None,
            confidence,
            valid_votes,
            "partial_payload_evidence",
        )
    if len(decoded) == 1:
        return _DecodeSummary(decoded.pop(), confidence, valid_votes, "decoded")
    statuses = {decision.status for decision in decisions}
    for status in (
        "geometry_rejected",
        "payload_not_detected",
        "insufficient_sync_evidence",
    ):
        if status in statuses:
            return _DecodeSummary(None, confidence, valid_votes, status)
    raise DemoVerificationError("DEMO_FINGERPRINT_DECODE_FAILED")


def _aggregate_unknown_page_decisions(
    decisions: list[DecodeV2Decision],
) -> _DecodeSummary:
    summary = _aggregate_decisions(decisions)
    if summary.status != "decoded":
        return summary
    consistent_support = sum(
        decision.status == "decoded" and decision.issuance_id == summary.issuance_id
        for decision in decisions
    )
    if (
        not isinstance(summary.issuance_id, uuid.UUID)
        or consistent_support < _UNKNOWN_PAGE_MIN_CONSISTENT_DECODES
    ):
        return _DecodeSummary(
            None,
            summary.confidence,
            summary.valid_votes,
            "partial_payload_evidence",
        )
    return summary


@transaction.atomic
def _commit_verification_result(
    *,
    claim: _ProcessingClaim,
    input_sha256: str,
    decode: _DecodeSummary,
    pages_analyzed: int,
    processing_ms: int,
    exact_only: bool = False,
) -> VerificationProcessingResult | None:
    job = _locked_job(claim.job_id)
    verification, upload = _locked_verification_upload(job)
    _validate_claim_binding(claim, job, verification, upload)
    result_record = _locked_result(claim)
    if job.status != JobStatus.PROCESSING:
        raise DemoVerificationError("DEMO_VERIFICATION_RESULT_INVALID")
    if job.cancel_requested_at is not None:
        _cancel_locked(job, result_record)
        return None

    source = _resolve_source_locked(
        organization_id=claim.organization_id,
        input_sha256=input_sha256,
        decode=decode,
        exact_only=exact_only,
    )
    limitations = tuple(dict.fromkeys((*_BASE_LIMITATIONS, *source.limitations)))
    if exact_only:
        # Preserve the already-migrated immutable demo evidence shape. The
        # release projection below replaces it with the narrower public claim.
        limitations = _BASE_LIMITATIONS
    evidence = {
        "algorithm_label": DEMO_ALGORITHM_LABEL,
        "decode_status": decode.status,
        "fingerprint_confidence": decode.confidence,
        "valid_vote_count": decode.valid_votes,
        "analyzed_page_count": pages_analyzed,
        "manifest_signature_valid": source.manifest_signature_valid,
        "exact_file_hash_match": source.exact_file_hash_match,
        "limitations": list(limitations),
    }
    metrics = {
        "processing_ms": processing_ms,
        "pages_processed": pages_analyzed,
        "cleanup_failures": 0,
    }
    completed_at = timezone.now()
    verification.recovered_issuance_id = source.recovered_issuance_id
    verification.status = source.status
    verification.evidence = evidence
    verification.metrics = metrics
    verification.completed_at = completed_at
    verification.save(
        update_fields=[
            "recovered_issuance",
            "status",
            "evidence",
            "metrics",
            "completed_at",
        ]
    )
    JobResultReceipt.objects.create(
        message_id=_receipt_id(job),
        organization_id=claim.organization_id,
        job=job,
    )
    result_record.result_state = DemoVerificationState.COMMITTED
    result_record.input_sha256 = input_sha256
    result_record.result_status = source.status
    result_record.recovered_issuance_id = source.recovered_issuance_id
    result_record.evidence = evidence
    result_record.metrics = metrics
    result_record.completed_at = completed_at
    with _allow_demo_result_write():
        result_record.save(
            update_fields=[
                "result_state",
                "input_sha256",
                "result_status",
                "recovered_issuance",
                "evidence",
                "metrics",
                "completed_at",
                "updated_at",
            ]
        )
    transition_job(job, JobStatus.SUCCEEDED)
    job.safe_error_code = None
    job.save(update_fields=["status", "safe_error_code", "updated_at"])
    return _result_from_record(result_record)


def _resolve_source_locked(
    *,
    organization_id: uuid.UUID,
    input_sha256: str,
    decode: _DecodeSummary,
    exact_only: bool = False,
) -> _SourceResolution:
    exact_candidates = list(
        Issuance.objects.select_for_update()
        .filter(organization_id=organization_id, output_sha256=input_sha256)
        .order_by("id")[:2]
    )
    if len(exact_candidates) == 1:
        issuance = exact_candidates[0]
        evidence_valid, manifest_valid = _validate_retained_source_locked(issuance)
        if evidence_valid and manifest_valid is True:
            limitations = (
                ("manifest.signed_evidence_unavailable",)
                if manifest_valid is None
                else ()
            )
            return _SourceResolution(
                VerificationStatus.VERIFIED_INTACT,
                issuance.id,
                True,
                manifest_valid,
                limitations,
            )
        if evidence_valid and manifest_valid is None and not exact_only:
            return _SourceResolution(
                VerificationStatus.VERIFIED_INTACT,
                issuance.id,
                True,
                None,
                ("manifest.signed_evidence_unavailable",),
            )
        return _SourceResolution(
            VerificationStatus.INVALID_MANIFEST,
            None,
            True,
            manifest_valid,
            ("evidence.retained_issuance_invalid",),
        )
    if len(exact_candidates) > 1:
        return _SourceResolution(
            VerificationStatus.PARTIAL_EVIDENCE,
            None,
            True,
            None,
            ("evidence.exact_hash_ambiguous", "manifest.signed_evidence_unavailable"),
        )
    if exact_only:
        return _SourceResolution(
            VerificationStatus.NO_WATERMARK,
            None,
            False,
            None,
            (TRANSFORMED_ATTRIBUTION_UNAVAILABLE,),
        )
    if decode.status == "decoded" and decode.issuance_id is not None:
        issuance = (
            Issuance.objects.select_for_update()
            .filter(organization_id=organization_id, pk=decode.issuance_id)
            .first()
        )
        if issuance is None:
            return _SourceResolution(
                VerificationStatus.PARTIAL_EVIDENCE,
                None,
                False,
                None,
                (
                    "fingerprint.decoded_source_not_available",
                    "manifest.signed_evidence_unavailable",
                ),
            )
        evidence_valid, manifest_valid = _validate_retained_source_locked(issuance)
        if not evidence_valid or manifest_valid is False:
            return _SourceResolution(
                VerificationStatus.INVALID_MANIFEST,
                None,
                False,
                manifest_valid,
                ("evidence.retained_issuance_invalid",),
            )
        limitations = (
            ("manifest.signed_evidence_unavailable",)
            if manifest_valid is None
            else ()
        )
        return _SourceResolution(
            VerificationStatus.SOURCE_IDENTIFIED_MODIFIED,
            issuance.id,
            False,
            manifest_valid,
            limitations,
        )
    if decode.status == "partial_payload_evidence":
        return _SourceResolution(
            VerificationStatus.PARTIAL_EVIDENCE,
            None,
            False,
            None,
            ("fingerprint.partial_payload_evidence", "manifest.signed_evidence_unavailable"),
        )
    return _SourceResolution(
        VerificationStatus.NO_WATERMARK,
        None,
        False,
        None,
        ("fingerprint.no_watermark_not_exclusion", "manifest.signed_evidence_unavailable"),
    )


def _validate_retained_source_locked(issuance: Issuance) -> tuple[bool, bool | None]:
    try:
        evidence = DemoIssuanceResult.objects.select_for_update().get(
            issuance_id=issuance.id,
            organization_id=issuance.organization_id,
        )
        source_job = (
            Job.objects.filter(issuance__isnull=False)
            .select_for_update(of=("self",))
            .get(pk=evidence.job_id)
        )
        document = Document.objects.select_for_update().get(pk=issuance.document_id)
        evidence.full_clean()
    except (DemoIssuanceResult.DoesNotExist, Job.DoesNotExist, Document.DoesNotExist, ValidationError):
        return False, None
    receipt_exists = JobResultReceipt.objects.select_for_update().filter(
        message_id=_issuance_receipt_id(source_job),
        organization_id=issuance.organization_id,
        job_id=source_job.id,
    ).exists()
    evidence_valid = (
        source_job.status == JobStatus.SUCCEEDED
        and evidence.output_state == DemoOutputState.COMMITTED
        and evidence.attempt == source_job.attempt
        and evidence.output_object_key == issuance.output_object_key
        and evidence.output_sha256 == issuance.output_sha256
        and evidence.page_count == document.page_count
        and receipt_exists
    )
    if not evidence_valid:
        return False, None

    try:
        manifest = Manifest.objects.select_for_update().get(
            issuance_id=issuance.id,
            organization_id=issuance.organization_id,
        )
    except Manifest.DoesNotExist:
        return True, None
    try:
        signing_key = SigningKey.objects.select_for_update().get(
            pk=manifest.signing_key_id,
            organization_id=issuance.organization_id,
        )
    except SigningKey.DoesNotExist:
        return True, False
    verification = verify_stored_manifest(
        manifest.public_payload,
        manifest.public_signature_envelope,
        signing_key,
        now=timezone.now(),
        expected_kind="public",
    )
    if not verification.trusted:
        return True, False
    try:
        payload = json.loads(manifest.public_payload)
    except (TypeError, ValueError):
        return True, False
    return True, (
        payload.get("issuance_id") == str(issuance.id)
        and payload.get("output_sha256") == issuance.output_sha256
    )


@transaction.atomic
def _record_failed_job(
    claim: _ProcessingClaim,
    error: DemoVerificationError,
    *,
    started: float,
) -> None:
    job = _locked_job(claim.job_id)
    verification, upload = _locked_verification_upload(job)
    _validate_claim_binding(claim, job, verification, upload)
    result_record = _locked_result(claim)
    if job.status != JobStatus.PROCESSING:
        return
    completed_at = timezone.now()
    evidence = {
        "algorithm_label": DEMO_ALGORITHM_LABEL,
        "decode_status": "execution_error",
        "fingerprint_confidence": 0.0,
        "valid_vote_count": 0,
        "analyzed_page_count": 0,
        "manifest_signature_valid": None,
        "exact_file_hash_match": None,
        "limitations": list(_BASE_LIMITATIONS),
    }
    metrics = {
        "processing_ms": max(0, round((time.monotonic() - started) * 1000)),
        "pages_processed": 0,
        "cleanup_failures": error.cleanup_failures,
    }
    verification.recovered_issuance = None
    verification.status = VerificationStatus.PROCESSING_FAILED
    verification.evidence = evidence
    verification.metrics = metrics
    verification.completed_at = completed_at
    verification.save(
        update_fields=[
            "recovered_issuance",
            "status",
            "evidence",
            "metrics",
            "completed_at",
        ]
    )
    result_record.result_state = DemoVerificationState.FAILED
    result_record.result_status = VerificationStatus.PROCESSING_FAILED
    result_record.evidence = evidence
    result_record.metrics = metrics
    result_record.safe_error_code = error.code
    result_record.completed_at = completed_at
    with _allow_demo_result_write():
        result_record.save(
            update_fields=[
                "result_state",
                "result_status",
                "evidence",
                "metrics",
                "safe_error_code",
                "completed_at",
                "updated_at",
            ]
        )
    transition_job(job, JobStatus.FAILED)
    job.safe_error_code = error.code
    job.save(update_fields=["status", "safe_error_code", "updated_at"])


@transaction.atomic
def _cancel_before_work(claim: _ProcessingClaim) -> bool:
    job = _locked_job(claim.job_id)
    verification, upload = _locked_verification_upload(job)
    _validate_claim_binding(claim, job, verification, upload)
    result_record = _locked_result(claim)
    if job.status != JobStatus.PROCESSING:
        raise DemoVerificationError("DEMO_VERIFICATION_RESULT_INVALID")
    if job.cancel_requested_at is None:
        return False
    _cancel_locked(job, result_record)
    return True


def _cleanup_workspace(workspace) -> int:
    try:
        workspace.cleanup()
    except Exception:
        return 1
    return 0


def _locked_job(job_id) -> Job:
    return (
        Job.objects.filter(verification__isnull=False)
        .select_for_update(of=("self",))
        .get(pk=job_id)
    )


def _locked_verification_upload(job: Job) -> tuple[Verification, UploadRequest]:
    verification = Verification.objects.select_for_update().get(pk=job.verification_id)
    upload = UploadRequest.objects.select_for_update().get(pk=verification.upload_request_id)
    return verification, upload


def _validate_locked_binding(
    job: Job, verification: Verification, upload: UploadRequest
) -> None:
    try:
        match = validate_promoted_key(upload.promotion_target_key)
    except (TypeError, ValueError) as error:
        raise DemoVerificationError("DEMO_VERIFICATION_JOB_INVALID") from error
    if (
        job.kind != JobKind.VERIFICATION
        or job.verification_id != verification.id
        or verification.organization_id != job.organization_id
        or upload.id != verification.upload_request_id
        or upload.organization_id != job.organization_id
        or upload.purpose != UploadPurpose.VERIFICATION
        or upload.promotion_status != PromotionStatus.ATTACHED
        or match.group("kind") != "verification"
        or match.group("organization") != str(job.organization_id)
        or match.group("upload") != str(upload.id)
    ):
        raise DemoVerificationError("DEMO_VERIFICATION_JOB_INVALID")


def _validate_claim_binding(
    claim: _ProcessingClaim,
    job: Job,
    verification: Verification,
    upload: UploadRequest,
) -> None:
    _validate_locked_binding(job, verification, upload)
    if (
        job.id != claim.job_id
        or job.organization_id != claim.organization_id
        or verification.id != claim.verification_id
        or upload.id != claim.upload_id
        or job.attempt != claim.attempt
        or upload.promotion_target_key != claim.input_object_key
        or upload.expected_sha256 != claim.expected_input_sha256
    ):
        raise DemoVerificationError("DEMO_VERIFICATION_OWNERSHIP_INVALID")


def _locked_result(claim: _ProcessingClaim) -> DemoVerificationResult:
    result_record = DemoVerificationResult.objects.select_for_update().get(
        job_id=claim.job_id
    )
    if (
        result_record.organization_id != claim.organization_id
        or result_record.verification_id != claim.verification_id
        or result_record.attempt != claim.attempt
        or result_record.owner_token != claim.owner_token
    ):
        raise DemoVerificationError("DEMO_VERIFICATION_OWNERSHIP_INVALID")
    return result_record


def _cancel_locked(job: Job, result_record: DemoVerificationResult) -> None:
    completed_at = timezone.now()
    transition_job(job, JobStatus.CANCELLED)
    job.safe_error_code = None
    job.save(update_fields=["status", "safe_error_code", "updated_at"])
    result_record.result_state = DemoVerificationState.CANCELLED
    result_record.evidence = {
        "algorithm_label": DEMO_ALGORITHM_LABEL,
        "decode_status": "cancelled",
        "limitations": list(_BASE_LIMITATIONS),
    }
    result_record.metrics = {"cleanup_failures": 0}
    result_record.safe_error_code = "DEMO_JOB_CANCELLED"
    result_record.completed_at = completed_at
    with _allow_demo_result_write():
        result_record.save(
            update_fields=[
                "result_state",
                "evidence",
                "metrics",
                "safe_error_code",
                "completed_at",
                "updated_at",
            ]
        )


def _receipt_id(job: Job) -> uuid.UUID:
    return uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"splitbind-demo-verification:{job.id}:{job.attempt}",
    )


def _load_replay_result(
    job: Job,
    verification: Verification,
    upload: UploadRequest,
) -> VerificationProcessingResult:
    result_record = DemoVerificationResult.objects.select_for_update().get(job_id=job.id)
    receipt_exists = JobResultReceipt.objects.select_for_update().filter(
        message_id=_receipt_id(job),
        organization_id=job.organization_id,
        job_id=job.id,
    ).exists()
    if (
        result_record.result_state != DemoVerificationState.COMMITTED
        or result_record.organization_id != job.organization_id
        or result_record.verification_id != verification.id
        or result_record.attempt != job.attempt
        or verification.status != result_record.result_status
        or verification.recovered_issuance_id != result_record.recovered_issuance_id
        or verification.evidence != result_record.evidence
        or verification.metrics != result_record.metrics
        or verification.completed_at != result_record.completed_at
        or upload.expected_sha256 != result_record.input_sha256
        or not receipt_exists
    ):
        raise DemoVerificationError("DEMO_VERIFICATION_RESULT_INVALID")
    if not integrity_release_enabled(getattr(settings, "SPLITBIND_RELEASE_MODE", None)):
        result_record.full_clean()
    return _result_from_record(result_record)


def _result_from_record(record: DemoVerificationResult) -> VerificationProcessingResult:
    evidence = record.evidence
    metrics = record.metrics
    integrity_mode = integrity_release_enabled(
        getattr(settings, "SPLITBIND_RELEASE_MODE", None)
    )
    fingerprint_enabled = bool(getattr(settings, "SPLITBIND_FINGERPRINT_ENABLED", False))
    limitations = tuple(evidence["limitations"])
    if integrity_mode:
        limitations = ("evidence.not_proof_of_leak_edit_or_distribution",)
        if fingerprint_enabled:
            limitations += (FINGERPRINT_BELOW_RELEASE_GATE,)
        elif evidence["exact_file_hash_match"] is not True:
            limitations += (TRANSFORMED_ATTRIBUTION_UNAVAILABLE,)
    return VerificationProcessingResult(
        organization_id=record.organization_id,
        job_id=record.job_id,
        verification_id=record.verification_id,
        status=record.result_status,
        recovered_issuance_id=record.recovered_issuance_id,
        input_sha256=record.input_sha256,
        algorithm_label=(
            INTEGRITY_ALGORITHM_LABEL
            if integrity_release_enabled(getattr(settings, "SPLITBIND_RELEASE_MODE", None))
            else evidence["algorithm_label"]
        ),
        decode_status=evidence["decode_status"],
        fingerprint_confidence=evidence["fingerprint_confidence"],
        valid_vote_count=evidence["valid_vote_count"],
        exact_file_hash_match=evidence["exact_file_hash_match"],
        manifest_signature_valid=evidence["manifest_signature_valid"],
        pages_analyzed=evidence["analyzed_page_count"],
        processing_ms=metrics["processing_ms"],
        limitations=limitations,
        cleanup_failures=metrics["cleanup_failures"],
    )
