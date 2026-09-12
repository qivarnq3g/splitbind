import hashlib
import importlib
import io
import struct
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import cv2
import django
import numpy as np
import pypdfium2 as pdfium
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, NumberObject
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import Client
from django.test import override_settings
from django.utils import timezone

django.setup()

from splitbind.access.models import Organization, Recipient, Role, SigningKey, User
from splitbind.demo.issuance import _build_issuance_pdf, _receipt_id, _select_frozen_candidate
from splitbind.demo.verification import (
    _decode_pdf,
    _pdf_page_metadata,
    _validate_pdf_raster_budget,
)
from splitbind.demo.models import (
    DEMO_CANONICAL_CANVAS,
    DEMO_FROZEN_CANDIDATE_IDENTIFIER,
    DEMO_LIMITATIONS,
    DemoIssuanceResult,
    DemoOutputState,
    _allow_demo_result_write,
)
from splitbind.documents.models import Document, Issuance, Manifest, Verification, VerificationStatus
from splitbind.integrations.storage.fake import FakeObjectStorage
from splitbind.jobs.models import Job, JobKind, JobResultReceipt, JobStatus
from splitbind.uploads.models import PromotionStatus, UploadPurpose, UploadRequest
from splitbind.release.manifest import build_signed_issuance_manifest, public_key_pem
from splitbind.release.mode import ReleaseMode

from .fixtures import (
    blank_pdf_bytes,
    encrypted_pdf_bytes,
    synthetic_image_bytes,
    synthetic_pdf_bytes,
)


FINGERPRINT_KEY = b"\x11" * 32
ISSUANCE_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")


@pytest.fixture(autouse=True)
def assert_task_workspaces_are_removed(monkeypatch, tmp_path):
    from splitbind.demo import verification as verification_module

    workspaces = []
    real_temporary_directory = tempfile.TemporaryDirectory

    def create_workspace(*args, **kwargs):
        kwargs["dir"] = tmp_path
        workspace = real_temporary_directory(*args, **kwargs)
        workspaces.append(Path(workspace.name))
        return workspace

    monkeypatch.setattr(
        verification_module.tempfile,
        "TemporaryDirectory",
        create_workspace,
    )
    yield workspaces
    assert all(not workspace.exists() for workspace in workspaces)


@pytest.fixture(scope="module")
def issued_pdf_bytes():
    output, page_count, candidate_identifier = _build_issuance_pdf(
        synthetic_pdf_bytes(),
        issuance_id=ISSUANCE_ID,
        fingerprint_key=FINGERPRINT_KEY,
    )
    assert page_count == 1
    assert candidate_identifier == DEMO_FROZEN_CANDIDATE_IDENTIFIER
    return output


@pytest.fixture(scope="module")
def issued_five_page_pdf_bytes():
    output, page_count, candidate_identifier = _build_issuance_pdf(
        synthetic_pdf_bytes(page_count=5),
        issuance_id=ISSUANCE_ID,
        fingerprint_key=FINGERPRINT_KEY,
    )
    assert page_count == 5
    assert candidate_identifier == DEMO_FROZEN_CANDIDATE_IDENTIFIER
    return output


def _issued_page_image(
    output: bytes, *, page_index: int, extension: str, render_scale: float = 2
) -> bytes:
    document = pdfium.PdfDocument(output)
    try:
        page = document[page_index]
        try:
            bitmap = page.render(
                scale=render_scale,
                fill_color=(255, 255, 255, 255),
                draw_annots=True,
            )
            try:
                raster = np.asarray(bitmap.to_numpy(), dtype=np.uint8).copy()
            finally:
                bitmap.close()
        finally:
            page.close()
    finally:
        document.close()
    if raster.shape[2] == 4:
        raster = raster[:, :, :3]
    options = [cv2.IMWRITE_JPEG_QUALITY, 100] if extension == ".jpg" else []
    encoded_ok, encoded = cv2.imencode(extension, raster, options)
    assert encoded_ok
    return encoded.tobytes()


def test_pdf_decode_honors_user_unit_for_equivalent_physical_page():
    output, _page_count, _candidate_id = _build_issuance_pdf(
        synthetic_pdf_bytes(), issuance_id=ISSUANCE_ID, fingerprint_key=FINGERPRINT_KEY
    )
    writer = PdfWriter(clone_from=io.BytesIO(output))
    page = writer.pages[0]
    page.scale_by(0.5)
    page[NameObject("/UserUnit")] = NumberObject(2)
    rewritten = io.BytesIO()
    writer.write(rewritten)
    candidate, _identifier = _select_frozen_candidate()

    decision, page_count = _decode_pdf(
        rewritten.getvalue(), fingerprint_key=FINGERPRINT_KEY, candidate=candidate
    )

    assert page_count == 1
    assert decision.status == "decoded"
    assert decision.issuance_id == ISSUANCE_ID


def test_forms_are_initialized_before_verification_page_count_access(monkeypatch):
    from splitbind.demo import verification as verification_module

    events = []

    class FormOrderedDocument:
        forms_initialized = False

        def init_forms(self):
            self.forms_initialized = True
            events.append("init_forms")

        def __len__(self):
            assert self.forms_initialized, "page count accessed before form initialization"
            events.append("len")
            return 0

        def close(self):
            events.append("close")

    monkeypatch.setattr(
        verification_module.pdfium,
        "PdfDocument",
        lambda _data: FormOrderedDocument(),
    )

    with pytest.raises(verification_module.DemoVerificationError, match="DEMO_PDF_PAGE_LIMIT"):
        _decode_pdf(b"%PDF-synthetic", fingerprint_key=FINGERPRINT_KEY, candidate=object())

    assert events == ["init_forms", "len", "close"]


def test_legacy_canonical_pages_use_72_dpi_compatibility_scale():
    output, _page_count, _candidate_id = _build_issuance_pdf(
        synthetic_pdf_bytes(page_count=4),
        issuance_id=ISSUANCE_ID,
        fingerprint_key=FINGERPRINT_KEY,
    )
    reader = PdfReader(io.BytesIO(output), strict=True)
    jpeg_pages = []
    for page in reader.pages:
        image = page["/Resources"]["/XObject"]["/Im0"].get_object()
        height, width = int(image["/Height"]), int(image["/Width"])
        rgb = np.frombuffer(image.get_data(), dtype=np.uint8).reshape(height, width, 3)
        canonical = cv2.resize(rgb, (1152, 2304), interpolation=cv2.INTER_CUBIC)
        encoded_ok, encoded = cv2.imencode(
            ".jpg",
            cv2.cvtColor(canonical, cv2.COLOR_RGB2BGR),
            [cv2.IMWRITE_JPEG_QUALITY, 95],
        )
        assert encoded_ok
        jpeg_pages.append(encoded.tobytes())
    legacy = _legacy_image_only_pdf(jpeg_pages)

    units, render_scales = _pdf_page_metadata(legacy, 4)

    assert units == (1.0, 1.0, 1.0, 1.0)
    assert render_scales == (1.0, 1.0, 1.0, 1.0)
    document = pdfium.PdfDocument(legacy)
    try:
        _validate_pdf_raster_budget(document, render_scales)
    finally:
        document.close()
    candidate, _identifier = _select_frozen_candidate()
    decision, page_count = _decode_pdf(
        legacy, fingerprint_key=FINGERPRINT_KEY, candidate=candidate
    )
    assert page_count == 4
    assert decision.status == "decoded"
    assert decision.issuance_id == ISSUANCE_ID


def test_noncanonical_legacy_page_content_uses_physical_144_dpi_scale():
    output, _page_count, _candidate_id = _build_issuance_pdf(
        synthetic_pdf_bytes(),
        issuance_id=ISSUANCE_ID,
        fingerprint_key=FINGERPRINT_KEY,
    )
    reader = PdfReader(io.BytesIO(output), strict=True)
    image = reader.pages[0]["/Resources"]["/XObject"]["/Im0"].get_object()
    height, width = int(image["/Height"]), int(image["/Width"])
    rgb = np.frombuffer(image.get_data(), dtype=np.uint8).reshape(height, width, 3)
    canonical = cv2.resize(rgb, (1152, 2304), interpolation=cv2.INTER_CUBIC)
    encoded_ok, encoded = cv2.imencode(
        ".jpg",
        cv2.cvtColor(canonical, cv2.COLOR_RGB2BGR),
        [cv2.IMWRITE_JPEG_QUALITY, 95],
    )
    assert encoded_ok
    half_page_content = b"q\n576 0 0 1152 0 0 cm\n/Im0 Do\nQ\n"
    noncanonical = _legacy_image_only_pdf(
        [encoded.tobytes()],
        page_content=half_page_content,
    )

    units, render_scales = _pdf_page_metadata(noncanonical, 1)

    assert units == (1.0,)
    assert render_scales == (2.0,)


@pytest.mark.parametrize(
    ("page_extra", "image_extra"),
    [
        (b" /Annots []", b""),
        (b"", b" /SMask null"),
        (b"", b" /Decode [0 1 0 1 0 1]"),
    ],
    ids=["annotations", "soft-mask", "decode-array"],
)
def test_legacy_compatibility_rejects_extra_page_or_image_entries(
    page_extra,
    image_extra,
):
    legacy_shape_with_extra = _legacy_image_only_pdf(
        [b"synthetic-jpeg"],
        page_extra=page_extra,
        image_extra=image_extra,
    )

    units, render_scales = _pdf_page_metadata(legacy_shape_with_extra, 1)

    assert units == (1.0,)
    assert render_scales == (2.0,)


def _legacy_image_only_pdf(
    jpeg_pages: list[bytes],
    *,
    page_content: bytes = b"q\n1152 0 0 2304 0 0 cm\n/Im0 Do\nQ\n",
    page_extra: bytes = b"",
    image_extra: bytes = b"",
) -> bytes:
    page_refs = [3 + index * 3 for index in range(len(jpeg_pages))]
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Count "
        + str(len(page_refs)).encode()
        + b" /Kids ["
        + b" ".join(f"{ref} 0 R".encode() for ref in page_refs)
        + b"] >>",
    ]
    for index, jpeg in enumerate(jpeg_pages):
        page_ref = page_refs[index]
        image_ref, content_ref = page_ref + 1, page_ref + 2
        content = page_content
        objects.extend(
            [
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 1152 2304] "
                b"/Resources << /XObject << /Im0 "
                + f"{image_ref} 0 R".encode()
                + b" >> >> /Contents "
                + f"{content_ref} 0 R".encode()
                + page_extra
                + b" >>",
                b"<< /Type /XObject /Subtype /Image /Width 1152 /Height 2304 "
                b"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length "
                + str(len(jpeg)).encode()
                + image_extra
                + b" >>\nstream\n"
                + jpeg
                + b"\nendstream",
                b"<< /Length "
                + str(len(content)).encode()
                + b" >>\nstream\n"
                + content
                + b"endstream",
            ]
        )
    result = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, 1):
        offsets.append(len(result))
        result.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    start = len(result)
    result.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        result.extend(f"{offset:010d} 00000 n \n".encode())
    result.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{start}\n%%EOF\n".encode()
    )
    return bytes(result)


def _promoted_upload(*, organization, actor, purpose, data):
    upload_id = uuid.uuid4()
    kind = "issuance" if purpose == UploadPurpose.ISSUANCE else "verification"
    expected_sha256 = hashlib.sha256(data).hexdigest()
    target = f"inputs/{kind}/{organization.id}/{upload_id}.bin"
    upload = UploadRequest.objects.create(
        id=upload_id,
        organization=organization,
        requested_by=actor,
        purpose=purpose,
        object_key=(
            f"uploads/orphan/{kind}_input/{organization.id}/{uuid.uuid4().hex}.bin"
        ),
        expected_sha256=expected_sha256,
        size_bytes=len(data),
        expires_at=timezone.now() + timedelta(minutes=15),
        finalized_at=timezone.now(),
        promotion_target_key=target,
        promotion_status=PromotionStatus.ATTACHED,
    )
    return upload, target, expected_sha256


def _record_committed_issuance(*, organization, actor, output, page_count=1):
    source = synthetic_pdf_bytes(page_count=page_count, width=144, height=192)
    upload, source_key, source_sha256 = _promoted_upload(
        organization=organization,
        actor=actor,
        purpose=UploadPurpose.ISSUANCE,
        data=source,
    )
    document = Document.objects.create(
        organization=organization,
        created_by=actor,
        upload_request=upload,
        source_object_key=source_key,
        expected_source_sha256=source_sha256,
        page_count=page_count,
    )
    recipient = Recipient.objects.create(
        organization=organization,
        external_reference=f"synthetic-{uuid.uuid4().hex[:8]}",
        display_name="Synthetic recipient",
    )
    output_sha256 = hashlib.sha256(output).hexdigest()
    issuance = Issuance.objects.create(
        id=ISSUANCE_ID,
        organization=organization,
        document=document,
        recipient=recipient,
        created_by=actor,
        output_object_key=f"outputs/issuance/{organization.id}/{ISSUANCE_ID}.pdf",
        output_sha256=output_sha256,
    )
    job = Job.objects.create(
        organization=organization,
        kind=JobKind.ISSUANCE,
        status=JobStatus.SUCCEEDED,
        attempt=0,
        issuance=issuance,
        deadline_at=timezone.now() + timedelta(minutes=10),
        correlation_id=uuid.uuid4(),
    )
    evidence = DemoIssuanceResult(
        organization=organization,
        job=job,
        issuance=issuance,
        attempt=job.attempt,
        owner_token=uuid.uuid4(),
        output_object_key=issuance.output_object_key,
        output_state=DemoOutputState.COMMITTED,
        algorithm_label="experimental_unreleased_fingerprint_v2",
        candidate_identifier=DEMO_FROZEN_CANDIDATE_IDENTIFIER,
        canvas_height=DEMO_CANONICAL_CANVAS[0],
        canvas_width=DEMO_CANONICAL_CANVAS[1],
        input_sha256=source_sha256,
        output_sha256=output_sha256,
        page_count=page_count,
        processing_ms=1,
        limitations=list(DEMO_LIMITATIONS),
    )
    with _allow_demo_result_write():
        evidence.save()
    JobResultReceipt.objects.create(
        message_id=_receipt_id(job),
        organization=organization,
        job=job,
    )
    return issuance


def _record_untrusted_output_hash(*, organization, actor, output):
    source = synthetic_pdf_bytes(width=144, height=192)
    upload, source_key, source_sha256 = _promoted_upload(
        organization=organization,
        actor=actor,
        purpose=UploadPurpose.ISSUANCE,
        data=source,
    )
    document = Document.objects.create(
        organization=organization,
        created_by=actor,
        upload_request=upload,
        source_object_key=source_key,
        expected_source_sha256=source_sha256,
        page_count=1,
    )
    recipient = Recipient.objects.create(
        organization=organization,
        external_reference=f"untrusted-{uuid.uuid4().hex[:8]}",
        display_name="Untrusted synthetic recipient",
    )
    return Issuance.objects.create(
        id=ISSUANCE_ID,
        organization=organization,
        document=document,
        recipient=recipient,
        created_by=actor,
        output_object_key=f"outputs/issuance/{organization.id}/{ISSUANCE_ID}.pdf",
        output_sha256=hashlib.sha256(output).hexdigest(),
    )


def _processing_verification(*, organization, actor, data, storage):
    upload, input_key, expected_sha256 = _promoted_upload(
        organization=organization,
        actor=actor,
        purpose=UploadPurpose.VERIFICATION,
        data=data,
    )
    verification = Verification.objects.create(
        organization=organization,
        upload_request=upload,
        requested_by=actor,
    )
    job = Job.objects.create(
        organization=organization,
        kind=JobKind.VERIFICATION,
        status=JobStatus.PROCESSING,
        attempt=0,
        verification=verification,
        deadline_at=timezone.now() + timedelta(minutes=10),
        correlation_id=uuid.uuid4(),
    )
    storage.inject_object_bytes(
        key=input_key,
        content_type="image/png",
        data=data,
        client_sha256_metadata=expected_sha256,
    )
    return job, verification


def _new_verification_context(data):
    organization = Organization.objects.create(
        name="Bounded verification",
        slug=f"bounded-{uuid.uuid4().hex[:8]}",
    )
    actor = User.objects.create_user(
        username=f"bounded-{uuid.uuid4().hex[:8]}",
        password="correct horse battery staple",
        organization=organization,
        role=Role.VERIFIER,
    )
    storage = FakeObjectStorage()
    job, verification = _processing_verification(
        organization=organization,
        actor=actor,
        data=data,
        storage=storage,
    )
    return job, verification, storage


def _assert_processing_failed(context, safe_error_code):
    job, verification, _storage = context
    job.refresh_from_db()
    verification.refresh_from_db()
    result_record = job.demo_verification_result
    assert job.status == JobStatus.FAILED
    assert job.safe_error_code == safe_error_code
    assert verification.status == VerificationStatus.PROCESSING_FAILED
    assert verification.recovered_issuance_id is None
    assert verification.completed_at is not None
    assert verification.evidence["decode_status"] == "execution_error"
    assert verification.evidence["manifest_signature_valid"] is None
    assert verification.evidence["exact_file_hash_match"] is None
    assert result_record.result_state == "failed"
    assert result_record.result_status == VerificationStatus.PROCESSING_FAILED
    assert result_record.safe_error_code == safe_error_code
    assert not JobResultReceipt.objects.filter(job=job).exists()


@pytest.mark.django_db
def test_integrity_release_non_exact_input_never_runs_hidden_fingerprint_decoder(monkeypatch):
    from splitbind.demo import verification as verification_module
    from splitbind.demo.verification import process_verification_job

    context = _new_verification_context(synthetic_image_bytes(extension=".png"))
    monkeypatch.setattr(
        verification_module,
        "_decode_content",
        lambda *args, **kwargs: pytest.fail("integrity release ran hidden fingerprint decode"),
    )
    with override_settings(
        SPLITBIND_DEMO_MODE=False,
        SPLITBIND_RELEASE_MODE=ReleaseMode.INTEGRITY_V1,
    ):
        result = process_verification_job(job_id=context[0].id, storage=context[2])

    assert result.status == VerificationStatus.NO_WATERMARK
    assert result.recovered_issuance_id is None
    assert result.exact_file_hash_match is False
    assert result.manifest_signature_valid is None
    assert "fingerprint.transformed_attribution_unavailable" in result.limitations


@pytest.mark.django_db
def test_integrity_release_exact_hash_requires_and_verifies_signed_manifest(monkeypatch):
    from splitbind.demo import verification as verification_module
    from splitbind.demo.verification import process_verification_job

    output = synthetic_pdf_bytes()
    organization = Organization.objects.create(
        name="Integrity exact verification",
        slug=f"integrity-exact-{uuid.uuid4().hex[:8]}",
    )
    actor = User.objects.create_user(
        username=f"integrity-{uuid.uuid4().hex[:8]}",
        password="correct horse battery staple",
        organization=organization,
        role=Role.VERIFIER,
    )
    issuance = _record_committed_issuance(
        organization=organization,
        actor=actor,
        output=output,
    )
    private_key = Ed25519PrivateKey.generate()
    signing_key = SigningKey.objects.create(
        organization=organization,
        key_id="integrity-key-1",
        public_key=public_key_pem(private_key),
        valid_from=issuance.issued_at - timedelta(seconds=1),
    )
    pair = build_signed_issuance_manifest(
        issuance_id=issuance.id,
        document_id=issuance.document_id,
        recipient_id=issuance.recipient_id,
        issued_at=issuance.issued_at,
        source_sha256=issuance.document.expected_source_sha256,
        output_sha256=issuance.output_sha256,
        signing_key_id=signing_key.key_id,
        private_key=private_key,
        retention_policy_id="retention-v1",
    )
    Manifest.objects.create(
        organization=organization,
        issuance=issuance,
        signing_key=signing_key,
        internal_payload=pair.internal_payload,
        internal_signature_envelope=pair.internal_signature_envelope,
        public_payload=pair.public_payload,
        public_signature_envelope=pair.public_signature_envelope,
    )
    storage = FakeObjectStorage()
    job, _verification = _processing_verification(
        organization=organization,
        actor=actor,
        data=output,
        storage=storage,
    )
    monkeypatch.setattr(
        verification_module,
        "_decode_content",
        lambda *args, **kwargs: pytest.fail("exact integrity verification decoded fingerprint"),
    )

    with override_settings(
        SPLITBIND_DEMO_MODE=False,
        SPLITBIND_RELEASE_MODE=ReleaseMode.INTEGRITY_V1,
    ):
        result = process_verification_job(job_id=job.id, storage=storage)

    assert result.status == VerificationStatus.VERIFIED_INTACT
    assert result.recovered_issuance_id == issuance.id
    assert result.exact_file_hash_match is True
    assert result.manifest_signature_valid is True


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_exact_same_organization_issued_output_is_verified_intact(
    issued_pdf_bytes,
    monkeypatch,
):
    from splitbind.demo.verification import process_verification_job

    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", FINGERPRINT_KEY.hex())
    organization = Organization.objects.create(
        name="Verification demo",
        slug=f"verification-{uuid.uuid4().hex[:8]}",
    )
    actor = User.objects.create_user(
        username=f"verifier-{uuid.uuid4().hex[:8]}",
        password="correct horse battery staple",
        organization=organization,
        role=Role.VERIFIER,
    )
    issuance = _record_committed_issuance(
        organization=organization,
        actor=actor,
        output=issued_pdf_bytes,
    )
    storage = FakeObjectStorage()
    job, verification = _processing_verification(
        organization=organization,
        actor=actor,
        data=issued_pdf_bytes,
        storage=storage,
    )

    result = process_verification_job(job_id=job.id, storage=storage)

    job.refresh_from_db()
    verification.refresh_from_db()
    assert result.status == VerificationStatus.VERIFIED_INTACT
    assert result.recovered_issuance_id == issuance.id
    assert result.input_sha256 == hashlib.sha256(issued_pdf_bytes).hexdigest()
    assert result.algorithm_label == "experimental_unreleased_fingerprint_v2"
    assert result.decode_status == "decoded"
    assert result.exact_file_hash_match is True
    assert result.manifest_signature_valid is None
    assert result.pages_analyzed == 1
    assert result.valid_vote_count >= 2
    assert result.cleanup_failures == 0
    assert job.status == JobStatus.SUCCEEDED
    assert job.safe_error_code is None
    assert verification.status == VerificationStatus.VERIFIED_INTACT
    assert verification.recovered_issuance_id == issuance.id
    assert verification.evidence["algorithm_label"] == result.algorithm_label
    assert verification.evidence["decode_status"] == result.decode_status
    assert verification.evidence["exact_file_hash_match"] is True
    assert verification.evidence["manifest_signature_valid"] is None
    assert verification.evidence["analyzed_page_count"] == 1
    assert "manifest.signed_evidence_unavailable" in verification.evidence["limitations"]
    assert verification.metrics["cleanup_failures"] == 0
    assert verification.completed_at is not None
    assert JobResultReceipt.objects.filter(job=job).count() == 1


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_unrelated_valid_png_uses_magic_not_metadata_and_never_attributes_source(
    issued_pdf_bytes,
    monkeypatch,
):
    from splitbind.demo.verification import process_verification_job

    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", FINGERPRINT_KEY.hex())
    organization = Organization.objects.create(
        name="Unrelated verification",
        slug=f"unrelated-{uuid.uuid4().hex[:8]}",
    )
    actor = User.objects.create_user(
        username=f"unrelated-{uuid.uuid4().hex[:8]}",
        password="correct horse battery staple",
        organization=organization,
        role=Role.VERIFIER,
    )
    _record_committed_issuance(
        organization=organization,
        actor=actor,
        output=issued_pdf_bytes,
    )
    unrelated_png = synthetic_image_bytes(extension=".png")
    storage = FakeObjectStorage()
    job, verification = _processing_verification(
        organization=organization,
        actor=actor,
        data=unrelated_png,
        storage=storage,
    )
    storage.objects[verification.upload_request.promotion_target_key] = (
        storage.objects[verification.upload_request.promotion_target_key].__class__(
            key=verification.upload_request.promotion_target_key,
            size_bytes=len(unrelated_png),
            content_type="application/pdf",
            client_sha256_metadata=hashlib.sha256(unrelated_png).hexdigest(),
        )
    )

    result = process_verification_job(job_id=job.id, storage=storage)

    job.refresh_from_db()
    verification.refresh_from_db()
    assert result.status == VerificationStatus.NO_WATERMARK
    assert result.recovered_issuance_id is None
    assert result.exact_file_hash_match is False
    assert result.decode_status in {
        "geometry_rejected",
        "payload_not_detected",
        "insufficient_sync_evidence",
    }
    assert result.pages_analyzed == 1
    assert job.status == JobStatus.SUCCEEDED
    assert verification.status == VerificationStatus.NO_WATERMARK
    assert verification.recovered_issuance_id is None
    assert verification.evidence["exact_file_hash_match"] is False
    assert "fingerprint.no_watermark_not_exclusion" in verification.evidence["limitations"]


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_verification_api_projects_constrained_fields_from_real_demo_evidence(
    monkeypatch,
):
    from splitbind.demo.verification import process_verification_job

    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", FINGERPRINT_KEY.hex())
    context = _new_verification_context(synthetic_image_bytes(extension=".png"))
    result = process_verification_job(job_id=context[0].id, storage=context[2])
    client = Client()
    client.force_login(context[1].requested_by)

    response = client.get(f"/api/v1/verifications/{context[1].id}")

    assert response.status_code == 200
    evidence = response.json()["evidence"]
    assert evidence["algorithm_label"] == "experimental_unreleased_fingerprint_v2"
    assert evidence["decode_status"] == result.decode_status
    assert evidence["limitations"][:4] == [
        "fingerprint.experimental_unreleased_v2",
        "fingerprint.not_gate_g1_evidence",
        "evidence.not_proof_of_leak_edit_or_distribution",
        "integrity.not_evaluated",
    ]


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_modified_issued_pdf_requires_real_decode_and_keeps_hash_fact_separate(
    issued_pdf_bytes,
    monkeypatch,
):
    from splitbind.demo.verification import process_verification_job

    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", FINGERPRINT_KEY.hex())
    organization = Organization.objects.create(
        name="Modified verification",
        slug=f"modified-{uuid.uuid4().hex[:8]}",
    )
    actor = User.objects.create_user(
        username=f"modified-{uuid.uuid4().hex[:8]}",
        password="correct horse battery staple",
        organization=organization,
        role=Role.VERIFIER,
    )
    issuance = _record_committed_issuance(
        organization=organization,
        actor=actor,
        output=issued_pdf_bytes,
    )
    modified = issued_pdf_bytes + b"\n% byte-level synthetic modification\n"
    storage = FakeObjectStorage()
    job, verification = _processing_verification(
        organization=organization,
        actor=actor,
        data=modified,
        storage=storage,
    )

    result = process_verification_job(job_id=job.id, storage=storage)

    verification.refresh_from_db()
    assert result.status == VerificationStatus.SOURCE_IDENTIFIED_MODIFIED
    assert result.recovered_issuance_id == issuance.id
    assert result.decode_status == "decoded"
    assert result.valid_vote_count >= 2
    assert result.exact_file_hash_match is False
    assert result.manifest_signature_valid is None
    assert verification.status == VerificationStatus.SOURCE_IDENTIFIED_MODIFIED
    assert verification.recovered_issuance_id == issuance.id
    assert verification.evidence["exact_file_hash_match"] is False
    assert "manifest.signed_evidence_unavailable" in verification.evidence["limitations"]


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
@pytest.mark.parametrize(
    ("extension", "page_index"),
    [(".png", 1), (".jpg", 4)],
)
def test_standalone_issued_page_does_not_attribute_from_one_page_index_hypothesis(
    issued_five_page_pdf_bytes,
    monkeypatch,
    extension,
    page_index,
):
    from splitbind.demo.verification import process_verification_job

    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", FINGERPRINT_KEY.hex())
    organization = Organization.objects.create(
        name="Standalone issued page",
        slug=f"standalone-{uuid.uuid4().hex[:8]}",
    )
    actor = User.objects.create_user(
        username=f"standalone-{uuid.uuid4().hex[:8]}",
        password="correct horse battery staple",
        organization=organization,
        role=Role.VERIFIER,
    )
    _record_committed_issuance(
        organization=organization,
        actor=actor,
        output=issued_five_page_pdf_bytes,
        page_count=5,
    )
    suspect = _issued_page_image(
        issued_five_page_pdf_bytes,
        page_index=page_index,
        extension=extension,
    )
    storage = FakeObjectStorage()
    job, verification = _processing_verification(
        organization=organization,
        actor=actor,
        data=suspect,
        storage=storage,
    )

    result = process_verification_job(job_id=job.id, storage=storage)

    verification.refresh_from_db()
    assert result.status == VerificationStatus.PARTIAL_EVIDENCE
    assert result.decode_status == "partial_payload_evidence"
    assert result.recovered_issuance_id is None
    assert result.pages_analyzed == 1
    assert verification.recovered_issuance_id is None


def test_unknown_page_index_requires_two_consistent_uuid_decodes():
    from splitbind.demo import verification as verification_module
    from splitbind_ref.fingerprint_v2 import DecodeV2Decision

    decisions = [
        DecodeV2Decision(ISSUANCE_ID, 0.9, 3, 0.0, "decoded"),
        DecodeV2Decision(ISSUANCE_ID, 0.8, 2, 0.0, "decoded"),
        DecodeV2Decision(None, 0.0, 0, None, "payload_not_detected"),
    ]

    summary = verification_module._aggregate_unknown_page_decisions(decisions)

    assert summary.status == "decoded"
    assert summary.issuance_id == ISSUANCE_ID
    assert summary.valid_votes == 5


def test_unknown_page_index_rejects_lone_uuid_decode():
    from splitbind.demo import verification as verification_module
    from splitbind_ref.fingerprint_v2 import DecodeV2Decision

    decisions = [
        DecodeV2Decision(ISSUANCE_ID, 0.9, 3, 0.0, "decoded"),
        DecodeV2Decision(None, 0.0, 0, None, "payload_not_detected"),
        DecodeV2Decision(None, 0.0, 0, None, "insufficient_sync_evidence"),
    ]

    summary = verification_module._aggregate_unknown_page_decisions(decisions)

    assert summary.status == "partial_payload_evidence"
    assert summary.issuance_id is None
    assert summary.valid_votes == 3


def test_unknown_page_index_rejects_consistent_non_uuid_values():
    from splitbind.demo import verification as verification_module
    from splitbind_ref.fingerprint_v2 import DecodeV2Decision

    decisions = [
        DecodeV2Decision("not-a-uuid", 0.9, 3, 0.0, "decoded"),
        DecodeV2Decision("not-a-uuid", 0.8, 2, 0.0, "decoded"),
    ]

    summary = verification_module._aggregate_unknown_page_decisions(decisions)

    assert summary.status == "partial_payload_evidence"
    assert summary.issuance_id is None
    assert summary.valid_votes == 5


def test_standalone_issued_page_with_wrong_key_never_attributes(
    issued_five_page_pdf_bytes,
):
    from splitbind.demo import verification as verification_module

    suspect = _issued_page_image(
        issued_five_page_pdf_bytes,
        page_index=2,
        extension=".png",
    )
    candidate, _identifier = _select_frozen_candidate()

    summary, page_count = verification_module._decode_content(
        suspect,
        fingerprint_key=b"wrong-key-material".ljust(32, b"!"),
        candidate=candidate,
    )

    assert page_count == 1
    assert summary.issuance_id is None
    assert summary.status != "decoded"


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_standalone_image_rejects_conflicting_page_index_decodes(monkeypatch):
    from splitbind.demo import verification as verification_module
    from splitbind.demo.verification import process_verification_job
    from splitbind_ref.fingerprint_v2 import DecodeV2Decision

    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", FINGERPRINT_KEY.hex())
    context = _new_verification_context(synthetic_image_bytes(extension=".png"))
    page_indices = []
    decisions = iter(
        (
            DecodeV2Decision(uuid.uuid4(), 0.9, 3, 0.0, "decoded"),
            DecodeV2Decision(uuid.uuid4(), 0.8, 3, 0.0, "decoded"),
            DecodeV2Decision(None, 0.0, 0, None, "insufficient_sync_evidence"),
            DecodeV2Decision(None, 0.0, 0, None, "insufficient_sync_evidence"),
            DecodeV2Decision(None, 0.0, 0, None, "insufficient_sync_evidence"),
        )
    )

    def conflicting_decode(_raster, _key, page_index, _canvas, _candidates):
        page_indices.append(page_index)
        return next(decisions)

    monkeypatch.setattr(
        verification_module,
        "decode_fingerprint_v2",
        conflicting_decode,
    )

    result = process_verification_job(job_id=context[0].id, storage=context[2])

    assert page_indices == [0, 1, 2, 3, 4]
    assert result.status == VerificationStatus.PARTIAL_EVIDENCE
    assert result.decode_status == "partial_payload_evidence"
    assert result.recovered_issuance_id is None


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_partial_payload_on_any_page_prevents_decoded_source_attribution(
    issued_pdf_bytes,
    monkeypatch,
):
    from splitbind.demo import verification as verification_module
    from splitbind.demo.verification import process_verification_job
    from splitbind_ref.fingerprint_v2 import DecodeV2Decision

    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", FINGERPRINT_KEY.hex())
    organization = Organization.objects.create(
        name="Conflicting multi-page verification",
        slug=f"conflicting-{uuid.uuid4().hex[:8]}",
    )
    actor = User.objects.create_user(
        username=f"conflicting-{uuid.uuid4().hex[:8]}",
        password="correct horse battery staple",
        organization=organization,
        role=Role.VERIFIER,
    )
    issuance = _record_committed_issuance(
        organization=organization,
        actor=actor,
        output=issued_pdf_bytes,
    )
    suspect = blank_pdf_bytes(page_sizes=((288, 384), (288, 384)))
    storage = FakeObjectStorage()
    job, verification = _processing_verification(
        organization=organization,
        actor=actor,
        data=suspect,
        storage=storage,
    )
    decisions = iter(
        (
            DecodeV2Decision(issuance.id, 0.9, 3, 0.0, "decoded"),
            DecodeV2Decision(None, 0.7, 2, None, "partial_payload_evidence"),
        )
    )
    monkeypatch.setattr(
        verification_module,
        "decode_fingerprint_v2",
        lambda *args, **kwargs: next(decisions),
    )

    result = process_verification_job(job_id=job.id, storage=storage)

    verification.refresh_from_db()
    assert result.status == VerificationStatus.PARTIAL_EVIDENCE
    assert result.decode_status == "partial_payload_evidence"
    assert result.recovered_issuance_id is None
    assert result.exact_file_hash_match is False
    assert result.pages_analyzed == 2
    assert result.valid_vote_count == 5
    assert verification.status == VerificationStatus.PARTIAL_EVIDENCE
    assert verification.recovered_issuance_id is None


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_unrelated_valid_jpeg_is_decoded_with_opencv(monkeypatch):
    from splitbind.demo.verification import process_verification_job

    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", FINGERPRINT_KEY.hex())
    context = _new_verification_context(synthetic_image_bytes(extension=".jpg"))

    result = process_verification_job(job_id=context[0].id, storage=context[2])

    assert result.status == VerificationStatus.NO_WATERMARK
    assert result.recovered_issuance_id is None
    assert result.exact_file_hash_match is False
    assert result.pages_analyzed == 1


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
@pytest.mark.parametrize(
    ("malformed", "safe_error_code"),
    [
        (b"not a supported input", "DEMO_INPUT_FORMAT_INVALID"),
        (b"%PDF-broken", "DEMO_PDF_INVALID"),
        (b"\x89PNG\r\n\x1a\nbroken", "DEMO_IMAGE_INVALID"),
        (b"\xff\xd8\xff\xe0broken", "DEMO_IMAGE_INVALID"),
    ],
)
def test_malformed_pdf_or_image_fails_safely(monkeypatch, malformed, safe_error_code):
    from splitbind.demo.verification import DemoVerificationError, process_verification_job

    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", FINGERPRINT_KEY.hex())
    context = _new_verification_context(malformed)

    with pytest.raises(DemoVerificationError, match=f"^{safe_error_code}$"):
        process_verification_job(job_id=context[0].id, storage=context[2])

    _assert_processing_failed(context, safe_error_code)


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_encrypted_pdf_fails_with_distinct_safe_code(monkeypatch):
    from splitbind.demo.verification import DemoVerificationError, process_verification_job

    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", FINGERPRINT_KEY.hex())
    context = _new_verification_context(encrypted_pdf_bytes())

    with pytest.raises(DemoVerificationError, match="^DEMO_PDF_ENCRYPTED$"):
        process_verification_job(job_id=context[0].id, storage=context[2])

    _assert_processing_failed(context, "DEMO_PDF_ENCRYPTED")


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_actual_checksum_mismatch_fails_before_decode(monkeypatch):
    from splitbind.demo.verification import DemoVerificationError, process_verification_job

    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", FINGERPRINT_KEY.hex())
    context = _new_verification_context(synthetic_pdf_bytes())
    input_key = context[1].upload_request.promotion_target_key
    context[2].object_bytes[input_key] = synthetic_pdf_bytes(width=144, height=192)

    with pytest.raises(DemoVerificationError, match="^DEMO_INPUT_CHECKSUM_MISMATCH$"):
        process_verification_job(job_id=context[0].id, storage=context[2])

    _assert_processing_failed(context, "DEMO_INPUT_CHECKSUM_MISMATCH")


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
@override_settings(MAX_PDF_BYTES=2048)
def test_actual_input_above_the_configured_byte_limit_fails_before_decode(monkeypatch):
    from splitbind.demo.verification import DemoVerificationError, process_verification_job

    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", FINGERPRINT_KEY.hex())
    context = _new_verification_context(synthetic_pdf_bytes())
    input_key = context[1].upload_request.promotion_target_key
    context[2].object_bytes[input_key] = b"%PDF-1.7\n" + b"x" * (10 * 1024 * 1024)

    with pytest.raises(DemoVerificationError, match="^DEMO_INPUT_FILE_LIMIT$"):
        process_verification_job(job_id=context[0].id, storage=context[2])

    _assert_processing_failed(context, "DEMO_INPUT_FILE_LIMIT")


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
@override_settings(MAX_PDF_PAGES=3)
def test_a_pdf_page_count_above_the_configured_limit_fails_before_rendering(monkeypatch):
    from splitbind.demo.verification import DemoVerificationError, process_verification_job

    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", FINGERPRINT_KEY.hex())
    context = _new_verification_context(
        blank_pdf_bytes(page_sizes=((288, 384),) * 4)
    )

    with pytest.raises(DemoVerificationError, match="^DEMO_PDF_PAGE_LIMIT$"):
        process_verification_job(job_id=context[0].id, storage=context[2])

    _assert_processing_failed(context, "DEMO_PDF_PAGE_LIMIT")


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
@pytest.mark.parametrize("kind", ["pdf", "png"])
def test_cumulative_raster_work_above_forty_megapixels_fails_preflight(
    monkeypatch,
    kind,
):
    from splitbind.demo.verification import DemoVerificationError, process_verification_job

    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", FINGERPRINT_KEY.hex())
    if kind == "pdf":
        data = blank_pdf_bytes(page_sizes=((7000, 6000),))
    else:
        oversized_header = bytearray(synthetic_image_bytes(extension=".png", width=8, height=8))
        struct.pack_into(">II", oversized_header, 16, 7000, 6000)
        data = bytes(oversized_header)
    context = _new_verification_context(data)

    with pytest.raises(DemoVerificationError, match="^DEMO_INPUT_RASTER_LIMIT$"):
        process_verification_job(job_id=context[0].id, storage=context[2])

    _assert_processing_failed(context, "DEMO_INPUT_RASTER_LIMIT")


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
@pytest.mark.parametrize("encoded_key", [None, "", "11" * 31, "AA" * 32, "gg" * 32])
def test_missing_or_noncanonical_key_fails_before_storage_read(
    monkeypatch,
    encoded_key,
):
    from splitbind.demo.verification import DemoVerificationError, process_verification_job

    if encoded_key is None:
        monkeypatch.delenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", raising=False)
    else:
        monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", encoded_key)
    context = _new_verification_context(synthetic_pdf_bytes())
    context[2].fail_next("download_bytes", "storage must remain unread")

    with pytest.raises(DemoVerificationError, match="^DEMO_FINGERPRINT_KEY_INVALID$"):
        process_verification_job(job_id=context[0].id, storage=context[2])

    _assert_processing_failed(context, "DEMO_FINGERPRINT_KEY_INVALID")


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_cancellation_before_work_reserves_owner_but_never_reads_storage(monkeypatch):
    from splitbind.demo.verification import DemoVerificationError, process_verification_job

    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", FINGERPRINT_KEY.hex())
    context = _new_verification_context(synthetic_pdf_bytes())
    Job.objects.filter(pk=context[0].id).update(cancel_requested_at=timezone.now())
    context[2].fail_next("download_bytes", "storage must remain unread")

    with pytest.raises(DemoVerificationError, match="^DEMO_JOB_CANCELLED$"):
        process_verification_job(job_id=context[0].id, storage=context[2])

    context[0].refresh_from_db()
    context[1].refresh_from_db()
    result_record = context[0].demo_verification_result
    assert context[0].status == JobStatus.CANCELLED
    assert context[0].safe_error_code is None
    assert context[1].status is None
    assert result_record.result_state == "cancelled"
    assert result_record.safe_error_code == "DEMO_JOB_CANCELLED"
    assert result_record.metrics == {"cleanup_failures": 0}
    assert not JobResultReceipt.objects.filter(job=context[0]).exists()


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_cancellation_after_claim_and_before_provider_read_skips_download(monkeypatch):
    from splitbind.demo import verification as verification_module
    from splitbind.demo.verification import DemoVerificationError, process_verification_job

    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", FINGERPRINT_KEY.hex())
    context = _new_verification_context(synthetic_pdf_bytes())
    real_load_key = verification_module._load_fingerprint_key
    real_download = context[2].download_bytes
    download_calls = 0

    def load_key_then_cancel():
        fingerprint_key = real_load_key()
        Job.objects.filter(pk=context[0].id).update(cancel_requested_at=timezone.now())
        return fingerprint_key

    def tracked_download(**kwargs):
        nonlocal download_calls
        download_calls += 1
        return real_download(**kwargs)

    monkeypatch.setattr(verification_module, "_load_fingerprint_key", load_key_then_cancel)
    monkeypatch.setattr(context[2], "download_bytes", tracked_download)

    with pytest.raises(DemoVerificationError, match="^DEMO_JOB_CANCELLED$"):
        process_verification_job(job_id=context[0].id, storage=context[2])

    context[0].refresh_from_db()
    context[1].refresh_from_db()
    assert download_calls == 0
    assert context[0].status == JobStatus.CANCELLED
    assert context[1].status is None
    assert context[0].demo_verification_result.result_state == "cancelled"
    assert not JobResultReceipt.objects.filter(job=context[0]).exists()


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_cancellation_after_download_is_rechecked_before_decode(monkeypatch):
    from splitbind.demo import verification as verification_module
    from splitbind.demo.verification import DemoVerificationError, process_verification_job

    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", FINGERPRINT_KEY.hex())
    context = _new_verification_context(synthetic_pdf_bytes())
    real_download = context[2].download_bytes

    def download_then_cancel(**kwargs):
        downloaded = real_download(**kwargs)
        Job.objects.filter(pk=context[0].id).update(cancel_requested_at=timezone.now())
        return downloaded

    def decode_must_not_run(*args, **kwargs):
        pytest.fail("decode ran after cancellation was visible")

    monkeypatch.setattr(context[2], "download_bytes", download_then_cancel)
    monkeypatch.setattr(verification_module, "_decode_content", decode_must_not_run)

    with pytest.raises(DemoVerificationError, match="^DEMO_JOB_CANCELLED$"):
        process_verification_job(job_id=context[0].id, storage=context[2])

    context[0].refresh_from_db()
    assert context[0].status == JobStatus.CANCELLED
    assert context[0].demo_verification_result.result_state == "cancelled"


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_cancellation_rechecked_before_result_commit(monkeypatch):
    from splitbind.demo import verification as verification_module
    from splitbind.demo.verification import DemoVerificationError, process_verification_job

    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", FINGERPRINT_KEY.hex())
    context = _new_verification_context(synthetic_image_bytes(extension=".png"))
    real_decode = verification_module._decode_content

    def decode_then_cancel(*args, **kwargs):
        decoded = real_decode(*args, **kwargs)
        Job.objects.filter(pk=context[0].id).update(cancel_requested_at=timezone.now())
        return decoded

    monkeypatch.setattr(verification_module, "_decode_content", decode_then_cancel)

    with pytest.raises(DemoVerificationError, match="^DEMO_JOB_CANCELLED$"):
        process_verification_job(job_id=context[0].id, storage=context[2])

    context[0].refresh_from_db()
    context[1].refresh_from_db()
    assert context[0].status == JobStatus.CANCELLED
    assert context[1].status is None
    assert context[0].demo_verification_result.result_state == "cancelled"
    assert not JobResultReceipt.objects.filter(job=context[0]).exists()


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_storage_provider_failure_is_safe_and_has_no_partial_result(monkeypatch):
    from splitbind.demo.verification import DemoVerificationError, process_verification_job

    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", FINGERPRINT_KEY.hex())
    context = _new_verification_context(synthetic_pdf_bytes())
    context[2].fail_next("download_bytes", "private provider detail")

    with pytest.raises(DemoVerificationError, match="^DEMO_INPUT_STORAGE_FAILED$"):
        process_verification_job(job_id=context[0].id, storage=context[2])

    _assert_processing_failed(context, "DEMO_INPUT_STORAGE_FAILED")
    assert "private provider detail" not in str(context[1].evidence)


@pytest.mark.django_db(transaction=True)
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_result_receipt_failure_rolls_back_success_atomically(monkeypatch):
    from splitbind.demo.verification import DemoVerificationError, process_verification_job

    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", FINGERPRINT_KEY.hex())
    context = _new_verification_context(synthetic_image_bytes(extension=".png"))

    def fail_receipt(*args, **kwargs):
        raise RuntimeError("synthetic database result failure")

    monkeypatch.setattr(JobResultReceipt.objects, "create", fail_receipt)

    with pytest.raises(DemoVerificationError, match="^DEMO_RESULT_COMMIT_FAILED$"):
        process_verification_job(job_id=context[0].id, storage=context[2])

    _assert_processing_failed(context, "DEMO_RESULT_COMMIT_FAILED")


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_reentrant_duplicate_cannot_overwrite_owner_result(monkeypatch):
    from splitbind.demo import verification as verification_module
    from splitbind.demo.verification import DemoVerificationError, process_verification_job

    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", FINGERPRINT_KEY.hex())
    context = _new_verification_context(synthetic_image_bytes(extension=".png"))
    real_decode = verification_module._decode_content
    duplicate_codes = []
    reentered = False

    def reenter_once(*args, **kwargs):
        nonlocal reentered
        if not reentered:
            reentered = True
            try:
                process_verification_job(job_id=context[0].id, storage=context[2])
            except DemoVerificationError as error:
                duplicate_codes.append(error.code)
        return real_decode(*args, **kwargs)

    monkeypatch.setattr(verification_module, "_decode_content", reenter_once)

    result = process_verification_job(job_id=context[0].id, storage=context[2])

    context[0].refresh_from_db()
    assert duplicate_codes == ["DEMO_JOB_RESULT_OWNED"]
    assert context[0].status == JobStatus.SUCCEEDED
    assert context[0].demo_verification_result.result_status == result.status
    assert JobResultReceipt.objects.filter(job=context[0]).count() == 1


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_successful_replay_returns_immutable_result_without_storage_access(monkeypatch):
    from splitbind.demo.verification import process_verification_job

    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", FINGERPRINT_KEY.hex())
    context = _new_verification_context(synthetic_image_bytes(extension=".png"))
    first = process_verification_job(job_id=context[0].id, storage=context[2])
    context[2].fail_next("download_bytes", "replay must not read storage")

    replay = process_verification_job(job_id=context[0].id, storage=context[2])

    assert replay == first
    assert JobResultReceipt.objects.filter(job=context[0]).count() == 1


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_decoded_issuance_outside_organization_is_only_partial_evidence(
    issued_pdf_bytes,
    monkeypatch,
):
    from splitbind.demo.verification import process_verification_job

    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", FINGERPRINT_KEY.hex())
    modified = issued_pdf_bytes + b"\n% cross-organization negative control\n"
    context = _new_verification_context(modified)

    result = process_verification_job(job_id=context[0].id, storage=context[2])

    context[1].refresh_from_db()
    assert result.decode_status == "decoded"
    assert result.status == VerificationStatus.PARTIAL_EVIDENCE
    assert result.recovered_issuance_id is None
    assert result.exact_file_hash_match is False
    assert context[1].recovered_issuance_id is None
    assert "fingerprint.decoded_source_not_available" in result.limitations


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_exact_hash_with_invalid_retained_demo_evidence_is_invalid_manifest(
    issued_pdf_bytes,
    monkeypatch,
):
    from splitbind.demo.verification import process_verification_job

    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", FINGERPRINT_KEY.hex())
    context = _new_verification_context(issued_pdf_bytes)
    _record_untrusted_output_hash(
        organization=context[1].organization,
        actor=context[1].requested_by,
        output=issued_pdf_bytes,
    )

    result = process_verification_job(job_id=context[0].id, storage=context[2])

    context[1].refresh_from_db()
    assert result.status == VerificationStatus.INVALID_MANIFEST
    assert result.exact_file_hash_match is True
    assert result.manifest_signature_valid is None
    assert result.recovered_issuance_id is None
    assert context[1].status == VerificationStatus.INVALID_MANIFEST
    assert context[1].recovered_issuance_id is None
    assert "evidence.retained_issuance_invalid" in result.limitations


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_workspace_cleanup_failure_is_terminal_and_counted(monkeypatch):
    from splitbind.demo import verification as verification_module
    from splitbind.demo.verification import DemoVerificationError, process_verification_job

    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", FINGERPRINT_KEY.hex())
    context = _new_verification_context(synthetic_image_bytes(extension=".png"))

    def cleanup_then_report_failure(workspace):
        workspace.cleanup()
        return 1

    monkeypatch.setattr(
        verification_module,
        "_cleanup_workspace",
        cleanup_then_report_failure,
    )

    with pytest.raises(DemoVerificationError, match="^DEMO_WORKSPACE_CLEANUP_FAILED$"):
        process_verification_job(job_id=context[0].id, storage=context[2])

    _assert_processing_failed(context, "DEMO_WORKSPACE_CLEANUP_FAILED")
    assert context[0].demo_verification_result.metrics["cleanup_failures"] == 1


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_committed_verification_owner_and_result_evidence_are_immutable(monkeypatch):
    from splitbind.demo.models import DemoVerificationResult
    from splitbind.demo.verification import process_verification_job

    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", FINGERPRINT_KEY.hex())
    context = _new_verification_context(synthetic_image_bytes(extension=".png"))
    process_verification_job(job_id=context[0].id, storage=context[2])
    result_record = DemoVerificationResult.objects.get(job_id=context[0].id)
    original_evidence = dict(result_record.evidence)

    result_record.evidence = {"algorithm_label": "forged"}
    with pytest.raises(ValidationError, match="immutable"):
        result_record.save(update_fields=["evidence"])
    with pytest.raises(ValidationError, match="immutable"):
        DemoVerificationResult.objects.filter(pk=result_record.pk).update(metrics={})
    with pytest.raises(ValidationError, match="preserved"):
        result_record.delete()

    result_record.refresh_from_db()
    assert result_record.evidence == original_evidence
    assert FINGERPRINT_KEY.hex() not in str(result_record.evidence)


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_reverse_migration_refuses_to_drop_durable_verification_evidence(monkeypatch):
    from splitbind.demo.verification import process_verification_job

    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", FINGERPRINT_KEY.hex())
    context = _new_verification_context(synthetic_image_bytes(extension=".png"))
    process_verification_job(job_id=context[0].id, storage=context[2])
    migration = importlib.import_module(
        "splitbind.demo.migrations.0002_demoverificationresult"
    )

    with pytest.raises(RuntimeError, match="verification result evidence"):
        migration.refuse_verification_evidence_rollback(
            apps,
            SimpleNamespace(connection=connection),
        )

    assert context[0].demo_verification_result.result_state == "committed"


@pytest.mark.django_db
def test_internal_capability_rejects_secret_bearing_committed_evidence():
    from splitbind.demo.models import (
        DemoVerificationResult,
        DemoVerificationState,
        _allow_demo_result_write,
    )

    data = synthetic_image_bytes(extension=".png")
    context = _new_verification_context(data)
    forged = DemoVerificationResult(
        organization=context[1].organization,
        job=context[0],
        verification=context[1],
        attempt=context[0].attempt,
        owner_token=uuid.uuid4(),
        result_state=DemoVerificationState.COMMITTED,
        input_sha256=hashlib.sha256(data).hexdigest(),
        result_status=VerificationStatus.NO_WATERMARK,
        evidence={
            "algorithm_label": "experimental_unreleased_fingerprint_v2",
            "private_secret": FINGERPRINT_KEY.hex(),
        },
        metrics={},
        completed_at=timezone.now(),
    )

    with _allow_demo_result_write(), pytest.raises(
        ValidationError,
        match="evidence shape",
    ):
        forged.save()

    assert not DemoVerificationResult.objects.filter(job=context[0]).exists()


@pytest.mark.django_db
def test_fingerprint_capability_is_off_unless_explicitly_enabled():
    from django.conf import settings

    assert settings.SPLITBIND_FINGERPRINT_ENABLED is False, (
        "the transformed-attribution capability must stay off by default; enabling it "
        "changes what the product claims about a document"
    )


@pytest.mark.django_db
@override_settings(
    SPLITBIND_DEMO_MODE=False,
    SPLITBIND_RELEASE_MODE=ReleaseMode.INTEGRITY_V1,
    SPLITBIND_FINGERPRINT_ENABLED=True,
)
def test_integrity_release_runs_the_fingerprint_decoder_once_the_capability_is_enabled(
    monkeypatch,
):
    from splitbind.demo import verification as verification_module
    from splitbind.demo.verification import process_verification_job

    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", FINGERPRINT_KEY.hex())
    context = _new_verification_context(synthetic_image_bytes(extension=".png"))
    observed = {}

    original = verification_module._decode_content

    def record(source, **kwargs):
        observed["ran"] = True
        observed["has_key"] = kwargs.get("fingerprint_key") is not None
        observed["has_candidate"] = kwargs.get("candidate") is not None
        return original(source, **kwargs)

    monkeypatch.setattr(verification_module, "_decode_content", record)

    result = process_verification_job(job_id=context[0].id, storage=context[2])

    assert observed.get("ran") is True, "the decoder never ran with the capability on"
    assert observed.get("has_key") is True
    assert observed.get("has_candidate") is True
    assert "fingerprint.transformed_attribution_unavailable" not in result.limitations
