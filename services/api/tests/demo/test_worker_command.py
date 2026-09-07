import hashlib
import io
import uuid
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from splitbind.access.models import Organization, Recipient, Role, User
from splitbind.demo import issuance as issuance_module
from splitbind.demo.issuance import _receipt_id as issuance_receipt_id
from splitbind.demo.models import (
    DEMO_CANONICAL_CANVAS,
    DEMO_FROZEN_CANDIDATE_IDENTIFIER,
    DEMO_LIMITATIONS,
    DEMO_STALE_RECOVERY_FENCE_CODE,
    DEMO_VERIFICATION_LIMITATIONS,
    DemoIssuanceResult,
    DemoOutputState,
    DemoVerificationResult,
    DemoVerificationState,
    _allow_demo_result_write,
)
from splitbind.demo.verification import _receipt_id as verification_receipt_id
from splitbind.documents.models import (
    Document,
    Issuance,
    Verification,
    VerificationStatus,
)
from splitbind.integrations.storage.fake import FakeObjectStorage
from splitbind.jobs.models import Job, JobKind, JobResultReceipt, JobStatus
from splitbind.outbox.services import create_job_event
from splitbind.uploads.models import PromotionStatus, UploadPurpose, UploadRequest

from .fixtures import synthetic_pdf_bytes


@pytest.fixture(autouse=True)
def worker_storage(monkeypatch):
    storage = FakeObjectStorage()
    monkeypatch.setattr(
        "splitbind.uploads.services.get_storage",
        lambda: storage,
    )
    return storage


def _created_issuance_job():
    source = synthetic_pdf_bytes(width=144, height=192)
    source_sha256 = hashlib.sha256(source).hexdigest()
    organization = Organization.objects.create(
        name="Demo worker",
        slug=f"demo-worker-{uuid.uuid4().hex[:8]}",
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
    input_key = f"inputs/issuance/{organization.id}/{upload_id}.bin"
    upload = UploadRequest.objects.create(
        id=upload_id,
        organization=organization,
        requested_by=actor,
        purpose=UploadPurpose.ISSUANCE,
        object_key=(
            f"uploads/orphan/issuance_input/{organization.id}/{uuid.uuid4().hex}.bin"
        ),
        expected_sha256=source_sha256,
        size_bytes=len(source),
        expires_at=timezone.now() + timedelta(minutes=15),
        finalized_at=timezone.now(),
        promotion_target_key=input_key,
        promotion_status=PromotionStatus.ATTACHED,
    )
    document = Document.objects.create(
        organization=organization,
        created_by=actor,
        upload_request=upload,
        source_object_key=input_key,
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
        status=JobStatus.CREATED,
        attempt=0,
        issuance=issuance,
        deadline_at=timezone.now() + timedelta(minutes=10),
        correlation_id=uuid.uuid4(),
    )
    event = create_job_event(
        job=job,
        input_object_key=input_key,
        input_sha256=source_sha256,
    )
    return job, event


def _created_verification_job():
    source = b"synthetic suspect"
    source_sha256 = hashlib.sha256(source).hexdigest()
    organization = Organization.objects.create(
        name="Demo verification worker",
        slug=f"demo-verify-worker-{uuid.uuid4().hex[:8]}",
    )
    actor = User.objects.create_user(
        username=f"verifier-{uuid.uuid4().hex[:8]}",
        password="correct horse battery staple",
        organization=organization,
        role=Role.VERIFIER,
    )
    upload_id = uuid.uuid4()
    input_key = f"inputs/verification/{organization.id}/{upload_id}.bin"
    upload = UploadRequest.objects.create(
        id=upload_id,
        organization=organization,
        requested_by=actor,
        purpose=UploadPurpose.VERIFICATION,
        object_key=(
            f"uploads/orphan/verification_input/{organization.id}/{uuid.uuid4().hex}.bin"
        ),
        expected_sha256=source_sha256,
        size_bytes=len(source),
        expires_at=timezone.now() + timedelta(minutes=15),
        finalized_at=timezone.now(),
        promotion_target_key=input_key,
        promotion_status=PromotionStatus.ATTACHED,
    )
    verification = Verification.objects.create(
        organization=organization,
        upload_request=upload,
        requested_by=actor,
    )
    job = Job.objects.create(
        organization=organization,
        kind=JobKind.VERIFICATION,
        status=JobStatus.CREATED,
        attempt=0,
        verification=verification,
        deadline_at=timezone.now() + timedelta(minutes=10),
        correlation_id=uuid.uuid4(),
    )
    event = create_job_event(
        job=job,
        input_object_key=input_key,
        input_sha256=source_sha256,
    )
    return job, event


def _make_stale(job, *, age=timedelta(minutes=16)):
    Job.objects.filter(pk=job.pk).update(
        status=JobStatus.PROCESSING,
        updated_at=timezone.now() - age,
    )
    job.refresh_from_db()
    return job


def _own_issuance(
    job,
    *,
    output_state=DemoOutputState.RESERVED,
    committed=False,
    input_sha256=None,
):
    issuance = Issuance.objects.get(pk=job.issuance_id)
    document = Document.objects.get(pk=issuance.document_id)
    output_key = f"outputs/issuance/{job.organization_id}/{issuance.id}.pdf"
    fields = {}
    if committed:
        issuance.output_object_key = output_key
        issuance.output_sha256 = "b" * 64
        issuance.save(update_fields=["output_object_key", "output_sha256"])
        document.page_count = 1
        document.save(update_fields=["page_count"])
        fields = {
            "algorithm_label": "experimental_unreleased_fingerprint_v2",
            "candidate_identifier": DEMO_FROZEN_CANDIDATE_IDENTIFIER,
            "canvas_height": DEMO_CANONICAL_CANVAS[0],
            "canvas_width": DEMO_CANONICAL_CANVAS[1],
            "input_sha256": input_sha256 or document.expected_source_sha256,
            "output_sha256": issuance.output_sha256,
            "page_count": 1,
            "processing_ms": 1,
            "limitations": list(DEMO_LIMITATIONS),
        }
    evidence = DemoIssuanceResult(
        organization_id=job.organization_id,
        job=job,
        issuance=issuance,
        attempt=job.attempt,
        owner_token=uuid.uuid4(),
        output_object_key=output_key,
        output_state=output_state,
        **fields,
    )
    with _allow_demo_result_write():
        evidence.save()
    if committed:
        JobResultReceipt.objects.create(
            message_id=issuance_receipt_id(job),
            organization_id=job.organization_id,
            job=job,
        )
    return evidence


def _own_verification(job, *, committed=False):
    verification = Verification.objects.get(pk=job.verification_id)
    completed_at = timezone.now() if committed else None
    evidence = {
        "algorithm_label": "experimental_unreleased_fingerprint_v2",
        "decode_status": "payload_not_detected",
        "fingerprint_confidence": 0.0,
        "valid_vote_count": 0,
        "analyzed_page_count": 1,
        "manifest_signature_valid": None,
        "exact_file_hash_match": False,
        "limitations": list(DEMO_VERIFICATION_LIMITATIONS),
    }
    metrics = {
        "processing_ms": 1,
        "pages_processed": 1,
        "cleanup_failures": 0,
    }
    if committed:
        verification.status = VerificationStatus.NO_WATERMARK
        verification.evidence = evidence
        verification.metrics = metrics
        verification.completed_at = completed_at
        verification.save(
            update_fields=["status", "evidence", "metrics", "completed_at"]
        )
    record = DemoVerificationResult(
        organization_id=job.organization_id,
        job=job,
        verification=verification,
        attempt=job.attempt,
        owner_token=uuid.uuid4(),
        result_state=(
            DemoVerificationState.COMMITTED
            if committed
            else DemoVerificationState.RESERVED
        ),
        input_sha256=(
            verification.upload_request.expected_sha256 if committed else None
        ),
        result_status=VerificationStatus.NO_WATERMARK if committed else None,
        evidence=evidence if committed else {},
        metrics=metrics if committed else {},
        completed_at=completed_at,
    )
    with _allow_demo_result_write():
        record.save()
    if committed:
        JobResultReceipt.objects.create(
            message_id=verification_receipt_id(job),
            organization_id=job.organization_id,
            job=job,
        )
    return record


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_once_stages_created_issuance_with_exact_unpublished_outbox_and_dispatches(
    monkeypatch,
):
    job, event = _created_issuance_job()
    storage = FakeObjectStorage()

    def process(*, job_id, storage):
        claimed = Job.objects.get(pk=job_id)
        assert claimed.status == JobStatus.PROCESSING
        claimed.status = JobStatus.SUCCEEDED
        claimed.save(update_fields=["status", "updated_at"])

    monkeypatch.setattr(
        "splitbind.uploads.services.get_storage",
        lambda: storage,
    )
    monkeypatch.setattr(
        "splitbind.demo.issuance.process_issuance_job",
        process,
    )

    stdout = io.StringIO()
    call_command("run_demo_worker", "--once", stdout=stdout)

    job.refresh_from_db()
    event.refresh_from_db()
    assert job.status == JobStatus.SUCCEEDED
    assert event.published_at is None
    assert "action=processed" in stdout.getvalue()
    assert str(job.id) in stdout.getvalue()


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_once_stages_and_dispatches_created_verification(monkeypatch):
    job, event = _created_verification_job()

    def process(*, job_id, storage):
        claimed = Job.objects.get(pk=job_id)
        assert claimed.status == JobStatus.PROCESSING
        claimed.status = JobStatus.SUCCEEDED
        claimed.save(update_fields=["status", "updated_at"])

    monkeypatch.setattr(
        "splitbind.demo.verification.process_verification_job",
        process,
    )

    call_command("run_demo_worker", "--once", stdout=io.StringIO())

    job.refresh_from_db()
    event.refresh_from_db()
    assert job.status == JobStatus.SUCCEEDED
    assert event.published_at is None


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_created_job_with_payload_not_bound_to_input_is_not_staged(monkeypatch):
    job, event = _created_issuance_job()
    payload = dict(event.payload)
    payload["input_sha256"] = "f" * 64
    event.payload = payload
    event.save(update_fields=["payload"])

    call_command("run_demo_worker", "--once", stdout=io.StringIO())

    job.refresh_from_db()
    event.refresh_from_db()
    assert job.status == JobStatus.CREATED
    assert event.published_at is None


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_once_processes_at_most_one_job_in_stable_order(monkeypatch):
    older, _older_event = _created_issuance_job()
    newer, _newer_event = _created_issuance_job()
    Job.objects.filter(pk=older.pk).update(
        created_at=timezone.now() - timedelta(minutes=1)
    )

    def process(*, job_id, storage):
        job = Job.objects.get(pk=job_id)
        job.status = JobStatus.SUCCEEDED
        job.save(update_fields=["status", "updated_at"])

    monkeypatch.setattr(
        "splitbind.demo.issuance.process_issuance_job",
        process,
    )

    call_command("run_demo_worker", "--once", stdout=io.StringIO())

    older.refresh_from_db()
    newer.refresh_from_db()
    assert older.status == JobStatus.SUCCEEDED
    assert newer.status == JobStatus.CREATED


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=False)
def test_disabled_command_fails_before_database_or_storage_access(monkeypatch):
    def forbidden_storage_access():
        raise AssertionError("storage must not be accessed")

    monkeypatch.setattr(
        "splitbind.uploads.services.get_storage",
        forbidden_storage_access,
    )

    with CaptureQueriesContext(connection) as queries:
        with pytest.raises(CommandError, match="^DEMO_MODE_DISABLED$"):
            call_command("run_demo_worker", "--once", stdout=io.StringIO())

    assert len(queries) == 0


@pytest.mark.parametrize("poll_interval", [0.09, 5.01])
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_poll_interval_outside_bounded_range_is_rejected(poll_interval):
    with pytest.raises(CommandError, match="^DEMO_POLL_INTERVAL_INVALID$"):
        call_command(
            "run_demo_worker",
            "--once",
            "--poll-interval",
            str(poll_interval),
            stdout=io.StringIO(),
        )


@override_settings(SPLITBIND_DEMO_MODE=True)
def test_continuous_mode_polls_with_bounded_interval_and_stops_cleanly(monkeypatch):
    calls = []

    monkeypatch.setattr(
        "splitbind.demo.management.commands.run_demo_worker.run_worker_cycle",
        lambda *, storage: calls.append("cycle"),
    )
    monkeypatch.setattr(
        "splitbind.demo.management.commands.run_demo_worker.reconcile_stale_jobs",
        lambda *, storage: (),
    )

    def interrupt_after_poll(seconds):
        calls.append(seconds)
        raise KeyboardInterrupt

    monkeypatch.setattr(
        "splitbind.demo.management.commands.run_demo_worker.time.sleep",
        interrupt_after_poll,
    )
    stdout = io.StringIO()

    call_command(
        "run_demo_worker",
        "--poll-interval",
        "0.25",
        stdout=stdout,
    )

    assert calls == ["cycle", 0.25]
    assert stdout.getvalue().strip() == "action=stopped code=INTERRUPTED"


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_processing_failure_is_logged_with_safe_code_only(monkeypatch):
    job, _event = _created_issuance_job()

    def fail_processing(*, job_id, storage):
        raise RuntimeError("provider-key=private exception detail")

    monkeypatch.setattr(
        "splitbind.demo.issuance.process_issuance_job",
        fail_processing,
    )
    stdout = io.StringIO()

    call_command("run_demo_worker", "--once", stdout=stdout)

    output = stdout.getvalue()
    assert "action=failed" in output
    assert f"job={job.id}" in output
    assert "kind=issuance" in output
    assert "code=DEMO_JOB_PROCESSING_FAILED" in output
    assert "provider-key" not in output
    assert "private" not in output


@override_settings(SPLITBIND_DEMO_MODE=True)
def test_storage_initialization_failure_uses_only_a_safe_command_error(monkeypatch):
    def fail_storage():
        raise RuntimeError("secret provider endpoint and credential")

    monkeypatch.setattr("splitbind.uploads.services.get_storage", fail_storage)

    with pytest.raises(CommandError, match="^DEMO_STORAGE_UNAVAILABLE$"):
        call_command("run_demo_worker", "--once", stdout=io.StringIO())


@override_settings(SPLITBIND_DEMO_MODE=True)
def test_interrupt_during_startup_recovery_exits_cleanly(monkeypatch):
    def interrupt(*, storage):
        raise KeyboardInterrupt

    monkeypatch.setattr(
        "splitbind.demo.management.commands.run_demo_worker.reconcile_stale_jobs",
        interrupt,
    )
    stdout = io.StringIO()

    call_command("run_demo_worker", stdout=stdout)

    assert stdout.getvalue().strip() == "action=stopped code=INTERRUPTED"


@override_settings(SPLITBIND_DEMO_MODE=True)
def test_once_hides_unexpected_cycle_failure_and_exits_safely(monkeypatch):
    monkeypatch.setattr(
        "splitbind.demo.management.commands.run_demo_worker.reconcile_stale_jobs",
        lambda *, storage: (),
    )

    def fail_cycle(*, storage):
        raise RuntimeError("database endpoint and credential detail")

    monkeypatch.setattr(
        "splitbind.demo.management.commands.run_demo_worker.run_worker_cycle",
        fail_cycle,
    )
    stdout = io.StringIO()

    call_command("run_demo_worker", "--once", stdout=stdout)

    output = stdout.getvalue().strip()
    assert output == "action=cycle code=DEMO_WORKER_CYCLE_FAILED"
    assert "credential" not in output


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_stale_committed_issuance_is_reconciled_to_success_without_deleting_output(
    worker_storage,
):
    job, _event = _created_issuance_job()
    job = _make_stale(job)
    evidence = _own_issuance(
        job,
        output_state=DemoOutputState.COMMITTED,
        committed=True,
    )
    worker_storage.inject_object_bytes(
        key=evidence.output_object_key,
        content_type="application/pdf",
        data=b"retained committed output",
        client_sha256_metadata="b" * 64,
    )

    call_command("run_demo_worker", "--once", stdout=io.StringIO())

    job.refresh_from_db()
    evidence.refresh_from_db()
    assert job.status == JobStatus.SUCCEEDED
    assert evidence.output_state == DemoOutputState.COMMITTED
    assert evidence.output_object_key in worker_storage.objects


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_stale_committed_verification_is_reconciled_to_success():
    job, _event = _created_verification_job()
    job = _make_stale(job)
    record = _own_verification(job, committed=True)

    call_command("run_demo_worker", "--once", stdout=io.StringIO())

    job.refresh_from_db()
    record.refresh_from_db()
    assert job.status == JobStatus.SUCCEEDED
    assert record.result_state == DemoVerificationState.COMMITTED


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_stale_verification_reservation_fails_with_durable_safe_evidence():
    job, _event = _created_verification_job()
    job = _make_stale(job)
    record = _own_verification(job)

    call_command("run_demo_worker", "--once", stdout=io.StringIO())

    job.refresh_from_db()
    record.refresh_from_db()
    verification = Verification.objects.get(pk=job.verification_id)
    assert job.status == JobStatus.FAILED
    assert job.safe_error_code == "DEMO_STALE_JOB_FAILED"
    assert record.result_state == DemoVerificationState.FAILED
    assert record.safe_error_code == "DEMO_STALE_JOB_FAILED"
    assert verification.status == VerificationStatus.PROCESSING_FAILED


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_stale_uploading_issuance_deletes_only_exact_owned_key_then_fails_safely(
    worker_storage,
):
    job, _event = _created_issuance_job()
    job = _make_stale(job)
    evidence = _own_issuance(job, output_state=DemoOutputState.UPLOADING)
    foreign_job, _foreign_event = _created_issuance_job()
    foreign_output = (
        f"outputs/issuance/{foreign_job.organization_id}/{foreign_job.issuance_id}.pdf"
    )
    worker_storage.inject_object_bytes(
        key=evidence.output_object_key,
        content_type="application/pdf",
        data=b"partial owned output",
        client_sha256_metadata="a" * 64,
    )
    worker_storage.inject_object_bytes(
        key=foreign_output,
        content_type="application/pdf",
        data=b"foreign output",
        client_sha256_metadata="c" * 64,
    )

    call_command("run_demo_worker", "--once", stdout=io.StringIO())

    job.refresh_from_db()
    evidence.refresh_from_db()
    assert job.status == JobStatus.FAILED
    assert job.safe_error_code == "DEMO_STALE_JOB_FAILED"
    assert evidence.output_state == DemoOutputState.CLEANUP_REQUIRED
    assert evidence.safe_error_code == DEMO_STALE_RECOVERY_FENCE_CODE
    assert evidence.output_object_key not in worker_storage.objects
    assert foreign_output in worker_storage.objects


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_stale_output_cleanup_failure_stays_durable_and_retries_exact_key(
    worker_storage,
):
    job, _event = _created_issuance_job()
    job = _make_stale(job)
    evidence = _own_issuance(job, output_state=DemoOutputState.UPLOADING)
    worker_storage.inject_object_bytes(
        key=evidence.output_object_key,
        content_type="application/pdf",
        data=b"partial output",
        client_sha256_metadata="a" * 64,
    )
    worker_storage.fail_next("delete", "provider credential detail")

    first_stdout = io.StringIO()
    call_command("run_demo_worker", "--once", stdout=first_stdout)

    job.refresh_from_db()
    evidence.refresh_from_db()
    assert job.status == JobStatus.PROCESSING
    assert evidence.output_state == DemoOutputState.CLEANUP_REQUIRED
    assert evidence.safe_error_code == "DEMO_STALE_OUTPUT_CLEANUP_FAILED"
    assert evidence.cleanup_failures == 1
    assert "credential" not in first_stdout.getvalue()

    call_command("run_demo_worker", "--once", stdout=io.StringIO())

    job.refresh_from_db()
    evidence.refresh_from_db()
    assert job.status == JobStatus.FAILED
    assert evidence.output_state == DemoOutputState.CLEANUP_REQUIRED
    assert evidence.safe_error_code == DEMO_STALE_RECOVERY_FENCE_CODE
    assert evidence.cleanup_failures == 1
    assert evidence.output_object_key not in worker_storage.objects


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_stale_recovery_does_not_rewrite_fresh_manually_unowned_or_mismatched_attempt_jobs():
    fresh, _fresh_event = _created_issuance_job()
    fresh.status = JobStatus.PROCESSING
    fresh.save(update_fields=["status", "updated_at"])
    _own_issuance(fresh)

    unowned, _unowned_event = _created_issuance_job()
    _make_stale(unowned)

    mismatched, _mismatched_event = _created_issuance_job()
    mismatched = _make_stale(mismatched)
    _own_issuance(mismatched)
    Job.objects.filter(pk=mismatched.pk).update(attempt=1)

    call_command("run_demo_worker", "--once", stdout=io.StringIO())

    fresh.refresh_from_db()
    unowned.refresh_from_db()
    mismatched.refresh_from_db()
    assert fresh.status == JobStatus.PROCESSING
    assert unowned.status == JobStatus.PROCESSING
    assert mismatched.status == JobStatus.PROCESSING


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
@pytest.mark.parametrize(
    ("factory", "result_relation", "terminal_state"),
    [
        (_created_issuance_job, "demo_issuance_result", DemoOutputState.CLEANED),
        (_created_verification_job, "demo_verification_result", DemoVerificationState.FAILED),
    ],
)
def test_crash_immediately_after_claim_has_durable_bounded_recovery(
    worker_storage,
    factory,
    result_relation,
    terminal_state,
):
    from splitbind.demo.worker import (
        claim_next_job,
        reconcile_stale_jobs,
        stage_next_created_job,
    )

    job, _event = factory()
    staged = stage_next_created_job()
    claimed = claim_next_job()

    assert staged is not None and staged.id == job.id
    assert claimed is not None and claimed.id == job.id
    owner = getattr(claimed, result_relation)
    assert owner.owner_token == claimed._demo_owner_token

    Job.objects.filter(pk=job.pk).update(
        updated_at=timezone.now() - timedelta(minutes=16),
    )
    outcomes = reconcile_stale_jobs(storage=worker_storage, limit=1)

    job.refresh_from_db()
    owner.refresh_from_db()
    assert len(outcomes) == 1
    assert outcomes[0].job_id == job.id
    assert job.status == JobStatus.FAILED
    assert job.safe_error_code == "DEMO_STALE_JOB_FAILED"
    state = (
        owner.output_state
        if isinstance(owner, DemoIssuanceResult)
        else owner.result_state
    )
    assert state == terminal_state


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_stale_reconciliation_is_bounded_and_uses_stable_order(worker_storage):
    older, _older_event = _created_verification_job()
    older = _make_stale(older, age=timedelta(minutes=18))
    _own_verification(older)
    newer, _newer_event = _created_verification_job()
    newer = _make_stale(newer, age=timedelta(minutes=17))
    _own_verification(newer)

    from splitbind.demo.worker import reconcile_stale_jobs

    outcomes = reconcile_stale_jobs(storage=worker_storage, limit=1)

    older.refresh_from_db()
    newer.refresh_from_db()
    assert len(outcomes) == 1
    assert older.status == JobStatus.FAILED
    assert newer.status == JobStatus.PROCESSING


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_stale_recovery_fences_original_commit_before_exact_output_delete(
    worker_storage,
    monkeypatch,
):
    job, _event = _created_issuance_job()
    job = _make_stale(job)
    evidence = _own_issuance(job, output_state=DemoOutputState.UPLOADING)
    issuance = Issuance.objects.get(pk=job.issuance_id)
    document = Document.objects.get(pk=issuance.document_id)
    claim = issuance_module._ProcessingClaim(
        job_id=job.id,
        organization_id=job.organization_id,
        issuance_id=issuance.id,
        document_id=document.id,
        attempt=job.attempt,
        source_object_key=document.source_object_key,
        expected_source_sha256=document.expected_source_sha256,
        output_object_key=evidence.output_object_key,
        owner_token=evidence.owner_token,
    )
    worker_storage.inject_object_bytes(
        key=evidence.output_object_key,
        content_type="application/pdf",
        data=b"original worker output",
        client_sha256_metadata="d" * 64,
    )
    observed_states = []
    commit_codes = []
    cleanup_codes = []
    original_delete = worker_storage.delete

    def original_worker_attempts_commit_during_delete(*, key):
        job.refresh_from_db()
        evidence.refresh_from_db()
        observed_states.append(
            (
                job.status,
                evidence.output_state,
                evidence.safe_error_code,
                evidence.owner_token != claim.owner_token,
            )
        )
        try:
            issuance_module._commit_issuance_result(
                claim=claim,
                input_sha256=document.expected_source_sha256,
                output_sha256="d" * 64,
                page_count=1,
                candidate_identifier=DEMO_FROZEN_CANDIDATE_IDENTIFIER,
                processing_ms=1,
            )
        except issuance_module.DemoIssuanceError as error:
            commit_codes.append(error.code)
            try:
                issuance_module._compensate_owned_output(
                    storage=worker_storage,
                    claim=claim,
                    cleaned_code="DEMO_RESULT_COMMIT_FAILED",
                    cleanup_failed_code="DEMO_RESULT_COMMIT_OUTPUT_CLEANUP_FAILED",
                )
            except issuance_module.DemoIssuanceError as cleanup_error:
                cleanup_codes.append(cleanup_error.code)
                issuance_module._record_failed_job(claim, cleanup_error)
        else:
            commit_codes.append("SUCCEEDED")
        job.refresh_from_db()
        observed_states.append((job.status,))
        original_delete(key=key)

    monkeypatch.setattr(
        worker_storage,
        "delete",
        original_worker_attempts_commit_during_delete,
    )

    from splitbind.demo.worker import reconcile_stale_jobs

    outcomes = reconcile_stale_jobs(storage=worker_storage)

    job.refresh_from_db()
    issuance.refresh_from_db()
    evidence.refresh_from_db()
    assert observed_states == [
        (
            JobStatus.PROCESSING,
            DemoOutputState.CLEANUP_REQUIRED,
            "DEMO_STALE_RECOVERY_FENCED",
            True,
        ),
        (JobStatus.PROCESSING,),
    ]
    assert commit_codes == ["DEMO_OUTPUT_OWNERSHIP_INVALID"]
    assert cleanup_codes == ["DEMO_OUTPUT_OWNERSHIP_INVALID"]
    assert outcomes[0].safe_code == "DEMO_STALE_JOB_FAILED"
    assert job.status == JobStatus.FAILED
    assert issuance.output_object_key is None
    assert issuance.output_sha256 is None
    assert evidence.output_state == DemoOutputState.CLEANUP_REQUIRED
    assert evidence.safe_error_code == DEMO_STALE_RECOVERY_FENCE_CODE
    assert evidence.output_object_key not in worker_storage.objects


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_stale_output_tombstone_redeletes_object_recreated_by_late_inflight_put(
    worker_storage,
    monkeypatch,
):
    job, _event = _created_issuance_job()
    job = _make_stale(job)
    evidence = _own_issuance(job, output_state=DemoOutputState.UPLOADING)
    worker_storage.inject_object_bytes(
        key=evidence.output_object_key,
        content_type="application/pdf",
        data=b"partial output before recovery",
        client_sha256_metadata="a" * 64,
    )
    original_delete = worker_storage.delete
    delete_count = 0

    def delete_then_finish_old_put(*, key):
        nonlocal delete_count
        delete_count += 1
        original_delete(key=key)
        if delete_count == 1:
            worker_storage.inject_object_bytes(
                key=key,
                content_type="application/pdf",
                data=b"late output from fenced owner",
                client_sha256_metadata="b" * 64,
            )

    monkeypatch.setattr(worker_storage, "delete", delete_then_finish_old_put)

    from splitbind.demo.worker import reconcile_stale_jobs

    first = reconcile_stale_jobs(storage=worker_storage, limit=1)

    job.refresh_from_db()
    evidence.refresh_from_db()
    assert len(first) == 1
    assert job.status == JobStatus.FAILED
    assert evidence.output_state == DemoOutputState.CLEANUP_REQUIRED
    assert evidence.safe_error_code == DEMO_STALE_RECOVERY_FENCE_CODE
    assert evidence.output_object_key in worker_storage.objects

    second = reconcile_stale_jobs(storage=worker_storage, limit=1)

    evidence.refresh_from_db()
    assert len(second) == 1
    assert second[0].job_id == job.id
    assert delete_count == 2
    assert evidence.output_state == DemoOutputState.CLEANUP_REQUIRED
    assert evidence.safe_error_code == DEMO_STALE_RECOVERY_FENCE_CODE
    assert evidence.output_object_key not in worker_storage.objects


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_stale_candidate_query_uses_exists_without_nullable_outer_join(worker_storage):
    from splitbind.demo.worker import reconcile_stale_jobs

    with CaptureQueriesContext(connection) as queries:
        reconcile_stale_jobs(storage=worker_storage, limit=1)

    candidate_sql = next(
        query["sql"]
        for query in queries.captured_queries
        if 'FROM "jobs_job"' in query["sql"]
    ).upper()
    assert "EXISTS" in candidate_sql
    assert "LEFT OUTER JOIN" not in candidate_sql


@pytest.mark.django_db(transaction=True)
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_postgresql_stale_candidate_lock_runtime_gate(worker_storage):
    if connection.vendor != "postgresql":
        pytest.skip(
            "SQLite cannot prove PostgreSQL FOR UPDATE OF or nullable-join behavior"
        )
    job, _event = _created_verification_job()
    job = _make_stale(job)
    _own_verification(job)

    from splitbind.demo.worker import reconcile_stale_jobs

    outcomes = reconcile_stale_jobs(storage=worker_storage, limit=1)

    job.refresh_from_db()
    assert outcomes[0].job_id == job.id
    assert job.status == JobStatus.FAILED


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_stale_committed_issuance_with_mismatched_input_hash_fails_and_keeps_output(
    worker_storage,
):
    job, _event = _created_issuance_job()
    job = _make_stale(job)
    evidence = _own_issuance(
        job,
        output_state=DemoOutputState.COMMITTED,
        committed=True,
        input_sha256="c" * 64,
    )
    worker_storage.inject_object_bytes(
        key=evidence.output_object_key,
        content_type="application/pdf",
        data=b"retained committed output",
        client_sha256_metadata="b" * 64,
    )

    call_command("run_demo_worker", "--once", stdout=io.StringIO())

    job.refresh_from_db()
    evidence.refresh_from_db()
    assert job.status == JobStatus.FAILED
    assert job.safe_error_code == "DEMO_STALE_RESULT_INVALID"
    assert evidence.output_state == DemoOutputState.COMMITTED
    assert evidence.output_object_key in worker_storage.objects
