import hashlib
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from django.test import override_settings
from django.utils import timezone

from splitbind.access.models import Organization, Recipient, Role, User
from splitbind.demo import issuance as issuance_module
from splitbind.demo.issuance import (
    FROZEN_CANDIDATE_IDENTIFIER_HEX,
    DemoIssuanceError,
    _build_issuance_pdf,
    process_issuance_job,
)
from splitbind.documents.models import Document, Issuance
from splitbind.integrations.storage.fake import FakeObjectStorage
from splitbind.jobs.models import Job, JobKind, JobResultReceipt, JobStatus
from splitbind.uploads.models import PromotionStatus, UploadPurpose, UploadRequest

from .fixtures import blank_pdf_bytes, encrypted_pdf_bytes, synthetic_pdf_bytes


@pytest.fixture
def processing_issuance(db):
    source_pdf = synthetic_pdf_bytes()
    source_sha256 = hashlib.sha256(source_pdf).hexdigest()
    organization = Organization.objects.create(
        name="Demo issuance",
        slug=f"demo-issuance-{uuid.uuid4().hex[:8]}",
    )
    actor = User.objects.create_user(
        username=f"issuer-{uuid.uuid4().hex[:8]}",
        password="correct horse battery staple",
        organization=organization,
        role=Role.ISSUER,
    )
    recipient = Recipient.objects.create(
        organization=organization,
        external_reference=f"synthetic-{uuid.uuid4().hex[:8]}",
        display_name="Synthetic recipient",
    )
    upload_id = uuid.uuid4()
    source_key = f"inputs/issuance/{organization.id}/{upload_id}.bin"
    upload = UploadRequest.objects.create(
        id=upload_id,
        organization=organization,
        requested_by=actor,
        purpose=UploadPurpose.ISSUANCE,
        object_key=(
            f"uploads/orphan/issuance_input/{organization.id}/{uuid.uuid4().hex}.bin"
        ),
        expected_sha256=source_sha256,
        size_bytes=len(source_pdf),
        expires_at=timezone.now() + timedelta(minutes=15),
        finalized_at=timezone.now(),
        promotion_target_key=source_key,
        promotion_status=PromotionStatus.ATTACHED,
    )
    document = Document.objects.create(
        organization=organization,
        created_by=actor,
        upload_request=upload,
        source_object_key=source_key,
        expected_source_sha256=source_sha256,
    )
    issuance = Issuance.objects.create(
        organization=organization,
        document=document,
        recipient=recipient,
        created_by=actor,
    )
    job = Job.objects.create(
        organization=organization,
        kind=JobKind.ISSUANCE,
        status=JobStatus.PROCESSING,
        attempt=0,
        issuance=issuance,
        deadline_at=timezone.now() + timedelta(minutes=10),
        correlation_id=uuid.uuid4(),
    )
    storage = FakeObjectStorage()
    storage.inject_object_bytes(
        key=source_key,
        content_type="application/pdf",
        data=source_pdf,
        client_sha256_metadata=source_sha256,
    )
    return job, issuance, document, storage


def replace_source(processing_issuance, data: bytes, *, update_expected: bool = True):
    job, issuance, document, storage = processing_issuance
    storage.object_bytes[document.source_object_key] = data
    if update_expected:
        document.expected_source_sha256 = hashlib.sha256(data).hexdigest()
        document.save(update_fields=["expected_source_sha256"])
    return job, issuance, document, storage


def assert_failed_without_result(processing_issuance, safe_error_code: str):
    job, issuance, document, storage = processing_issuance
    job.refresh_from_db()
    issuance.refresh_from_db()
    document.refresh_from_db()
    output_key = f"outputs/issuance/{issuance.organization_id}/{issuance.id}.pdf"
    assert job.status == JobStatus.FAILED
    assert job.safe_error_code == safe_error_code
    assert issuance.output_object_key is None
    assert issuance.output_sha256 is None
    assert document.page_count is None
    assert not JobResultReceipt.objects.filter(job_id=job.id).exists()
    assert output_key not in storage.objects
    assert output_key not in storage.object_bytes


def test_same_input_identity_and_key_produce_identical_output_bytes():
    source_pdf = synthetic_pdf_bytes()
    issuance_id = uuid.UUID("11111111-1111-4111-8111-111111111111")

    first = _build_issuance_pdf(
        source_pdf,
        issuance_id=issuance_id,
        fingerprint_key=b"k" * 32,
    )[0]
    second = _build_issuance_pdf(
        source_pdf,
        issuance_id=issuance_id,
        fingerprint_key=b"k" * 32,
    )[0]

    assert first == second


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_real_one_page_issuance_stores_image_only_pdf_and_commits_exact_result(
    processing_issuance,
    monkeypatch,
):
    job, issuance, document, storage = processing_issuance
    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", "11" * 32)

    result = process_issuance_job(job_id=job.id, storage=storage)

    job.refresh_from_db()
    issuance.refresh_from_db()
    document.refresh_from_db()
    output_bytes = storage.object_bytes[issuance.output_object_key]
    actual_output_sha256 = hashlib.sha256(output_bytes).hexdigest()

    assert job.status == JobStatus.SUCCEEDED
    assert job.safe_error_code is None
    assert issuance.output_object_key == (
        f"outputs/issuance/{issuance.organization_id}/{issuance.id}.pdf"
    )
    assert issuance.output_sha256 == actual_output_sha256 == result.output_sha256
    assert document.page_count == result.pages_processed == 1
    assert JobResultReceipt.objects.filter(
        organization_id=issuance.organization_id,
        job_id=job.id,
    ).count() == 1
    assert result.algorithm_label == "experimental_unreleased_fingerprint_v2"
    assert result.candidate_identifier == FROZEN_CANDIDATE_IDENTIFIER_HEX
    assert result.canonical_canvas == (2304, 1152)
    assert result.limitations == (
        "fingerprint.experimental_unreleased_v2",
        "fingerprint.not_gate_g1_evidence",
        "evidence.not_proof_of_leak_edit_or_distribution",
    )

    output_pdf = pdfium.PdfDocument(output_bytes)
    try:
        assert len(output_pdf) == 1
        page = output_pdf[0]
        try:
            assert page.get_size() == (1152.0, 2304.0)
            assert [item.type for item in page.get_objects()] == [
                pdfium.raw.FPDF_PAGEOBJ_IMAGE
            ]
            text_page = page.get_textpage()
            try:
                assert text_page.count_chars() == 0
            finally:
                text_page.close()
            rendered = page.render(scale=1)
            try:
                assert (rendered.height, rendered.width) == (2304, 1152)
            finally:
                rendered.close()
        finally:
            page.close()
    finally:
        output_pdf.close()


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_task_workspace_survives_through_upload_then_is_removed(
    processing_issuance,
    monkeypatch,
    tmp_path,
):
    job, _issuance, _document, storage = processing_issuance
    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", "11" * 32)
    workspaces = []
    real_temporary_directory = tempfile.TemporaryDirectory

    def create_workspace(*args, **kwargs):
        kwargs["dir"] = tmp_path
        workspace = real_temporary_directory(*args, **kwargs)
        workspaces.append(Path(workspace.name))
        return workspace

    monkeypatch.setattr(issuance_module.tempfile, "TemporaryDirectory", create_workspace)
    real_upload = storage.upload_bytes

    def assert_workspace_then_upload(**kwargs):
        workspace_path = workspaces[0]
        assert workspace_path.is_dir()
        assert (workspace_path / "source.pdf").is_file()
        assert (workspace_path / "output.pdf").is_file()
        return real_upload(**kwargs)

    monkeypatch.setattr(storage, "upload_bytes", assert_workspace_then_upload)

    result = process_issuance_job(job_id=job.id, storage=storage)

    assert result.cleanup_failures == 0
    assert len(workspaces) == 1
    assert not workspaces[0].exists()


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
@pytest.mark.parametrize("source_pdf", [b"not a pdf", b"%PDF-broken"])
def test_malformed_or_non_pdf_bytes_fail_safely(
    processing_issuance,
    monkeypatch,
    source_pdf,
):
    replace_source(processing_issuance, source_pdf)
    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", "11" * 32)

    with pytest.raises(DemoIssuanceError, match="^DEMO_PDF_INVALID$"):
        process_issuance_job(job_id=processing_issuance[0].id, storage=processing_issuance[3])

    assert_failed_without_result(processing_issuance, "DEMO_PDF_INVALID")


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_encrypted_pdf_fails_with_distinct_safe_code(processing_issuance, monkeypatch):
    replace_source(processing_issuance, encrypted_pdf_bytes())
    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", "11" * 32)

    with pytest.raises(DemoIssuanceError, match="^DEMO_PDF_ENCRYPTED$"):
        process_issuance_job(job_id=processing_issuance[0].id, storage=processing_issuance[3])

    assert_failed_without_result(processing_issuance, "DEMO_PDF_ENCRYPTED")


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_actual_checksum_mismatch_fails_before_pdf_processing(processing_issuance, monkeypatch):
    replace_source(
        processing_issuance,
        synthetic_pdf_bytes(width=144, height=192),
        update_expected=False,
    )
    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", "11" * 32)

    with pytest.raises(DemoIssuanceError, match="^DEMO_INPUT_CHECKSUM_MISMATCH$"):
        process_issuance_job(job_id=processing_issuance[0].id, storage=processing_issuance[3])

    assert_failed_without_result(processing_issuance, "DEMO_INPUT_CHECKSUM_MISMATCH")


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_more_than_five_pages_fails_before_rendering(processing_issuance, monkeypatch):
    replace_source(
        processing_issuance,
        blank_pdf_bytes(page_sizes=((288, 384),) * 6),
    )
    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", "11" * 32)

    with pytest.raises(DemoIssuanceError, match="^DEMO_PDF_PAGE_LIMIT$"):
        process_issuance_job(job_id=processing_issuance[0].id, storage=processing_issuance[3])

    assert_failed_without_result(processing_issuance, "DEMO_PDF_PAGE_LIMIT")


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_actual_input_above_ten_mib_fails_before_hash_acceptance(processing_issuance, monkeypatch):
    oversized = b"%PDF-1.7\n" + b"x" * (10 * 1024 * 1024)
    replace_source(processing_issuance, oversized)
    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", "11" * 32)

    with pytest.raises(DemoIssuanceError, match="^DEMO_PDF_FILE_LIMIT$"):
        process_issuance_job(job_id=processing_issuance[0].id, storage=processing_issuance[3])

    assert_failed_without_result(processing_issuance, "DEMO_PDF_FILE_LIMIT")


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_cumulative_raster_work_above_forty_megapixels_fails_before_rendering(
    processing_issuance,
    monkeypatch,
):
    replace_source(
        processing_issuance,
        blank_pdf_bytes(page_sizes=((4000, 3000),)),
    )
    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", "11" * 32)

    with pytest.raises(DemoIssuanceError, match="^DEMO_PDF_RASTER_LIMIT$"):
        process_issuance_job(job_id=processing_issuance[0].id, storage=processing_issuance[3])

    assert_failed_without_result(processing_issuance, "DEMO_PDF_RASTER_LIMIT")


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
@pytest.mark.parametrize("encoded_key", [None, "", "11" * 31, "AA" * 32, "gg" * 32])
def test_missing_or_noncanonical_demo_key_fails_before_storage_read(
    processing_issuance,
    monkeypatch,
    encoded_key,
):
    if encoded_key is None:
        monkeypatch.delenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", raising=False)
    else:
        monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", encoded_key)
    processing_issuance[3].fail_next("download_bytes", "must remain unread")

    with pytest.raises(DemoIssuanceError, match="^DEMO_FINGERPRINT_KEY_INVALID$"):
        process_issuance_job(job_id=processing_issuance[0].id, storage=processing_issuance[3])

    assert_failed_without_result(processing_issuance, "DEMO_FINGERPRINT_KEY_INVALID")


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_output_provider_failure_never_claims_partial_success(processing_issuance, monkeypatch):
    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", "11" * 32)
    processing_issuance[3].fail_next("upload_bytes", "private provider detail")

    with pytest.raises(DemoIssuanceError, match="^DEMO_OUTPUT_STORAGE_FAILED$"):
        process_issuance_job(job_id=processing_issuance[0].id, storage=processing_issuance[3])

    assert_failed_without_result(processing_issuance, "DEMO_OUTPUT_STORAGE_FAILED")


@pytest.mark.django_db(transaction=True)
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_result_commit_failure_rolls_back_database_and_compensates_exact_output(
    processing_issuance,
    monkeypatch,
):
    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", "11" * 32)

    def fail_receipt(*args, **kwargs):
        raise RuntimeError("synthetic database failure")

    monkeypatch.setattr(JobResultReceipt.objects, "create", fail_receipt)

    with pytest.raises(DemoIssuanceError, match="^DEMO_RESULT_COMMIT_FAILED$"):
        process_issuance_job(job_id=processing_issuance[0].id, storage=processing_issuance[3])

    assert_failed_without_result(processing_issuance, "DEMO_RESULT_COMMIT_FAILED")


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_cancellation_rechecked_before_commit_deletes_uploaded_output(
    processing_issuance,
    monkeypatch,
):
    job, issuance, document, storage = processing_issuance
    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", "11" * 32)
    real_upload = storage.upload_bytes

    def upload_then_cancel(**kwargs):
        uploaded = real_upload(**kwargs)
        Job.objects.filter(pk=job.id).update(cancel_requested_at=timezone.now())
        return uploaded

    monkeypatch.setattr(storage, "upload_bytes", upload_then_cancel)

    with pytest.raises(DemoIssuanceError, match="^DEMO_JOB_CANCELLED$"):
        process_issuance_job(job_id=job.id, storage=storage)

    job.refresh_from_db()
    issuance.refresh_from_db()
    document.refresh_from_db()
    output_key = f"outputs/issuance/{issuance.organization_id}/{issuance.id}.pdf"
    assert job.status == JobStatus.CANCELLED
    assert job.safe_error_code is None
    assert issuance.output_object_key is None
    assert issuance.output_sha256 is None
    assert document.page_count is None
    assert not JobResultReceipt.objects.filter(job_id=job.id).exists()
    assert output_key not in storage.objects


@pytest.mark.django_db(transaction=True)
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_failed_result_compensation_is_reported_without_marking_success(
    processing_issuance,
    monkeypatch,
):
    monkeypatch.setenv("SPLITBIND_DEMO_FINGERPRINT_KEY_HEX", "11" * 32)

    def fail_receipt(*args, **kwargs):
        raise RuntimeError("synthetic database failure")

    monkeypatch.setattr(JobResultReceipt.objects, "create", fail_receipt)
    processing_issuance[3].fail_next("delete", "private cleanup detail")

    with pytest.raises(
        DemoIssuanceError,
        match="^DEMO_RESULT_COMMIT_OUTPUT_CLEANUP_FAILED$",
    ) as captured:
        process_issuance_job(job_id=processing_issuance[0].id, storage=processing_issuance[3])

    assert captured.value.cleanup_failures == 1
    job, issuance, document, storage = processing_issuance
    job.refresh_from_db()
    issuance.refresh_from_db()
    document.refresh_from_db()
    output_key = f"outputs/issuance/{issuance.organization_id}/{issuance.id}.pdf"
    assert job.status == JobStatus.FAILED
    assert job.safe_error_code == "DEMO_RESULT_COMMIT_OUTPUT_CLEANUP_FAILED"
    assert issuance.output_object_key is None
    assert issuance.output_sha256 is None
    assert document.page_count is None
    assert not JobResultReceipt.objects.filter(job_id=job.id).exists()
    assert output_key in storage.objects
