import uuid
from contextlib import contextmanager
from datetime import timedelta

import pytest
from django.test import override_settings
from django.utils import timezone

import splitbind.demo.worker as demo_worker
from splitbind.access.models import Organization, Role, User
from splitbind.demo.worker import claim_next_job
from splitbind.documents.models import Verification
from splitbind.jobs.models import Job, JobKind, JobStatus
from splitbind.uploads.models import UploadPurpose, UploadRequest


@pytest.fixture
def claim_context(db):
    organization = Organization.objects.create(
        name="Demo claim",
        slug=f"demo-claim-{uuid.uuid4().hex[:8]}",
    )
    actor = User.objects.create_user(
        username=f"verifier-{uuid.uuid4().hex[:8]}",
        password="correct horse battery staple",
        organization=organization,
        role=Role.VERIFIER,
    )
    upload = UploadRequest.objects.create(
        organization=organization,
        requested_by=actor,
        purpose=UploadPurpose.VERIFICATION,
        object_key=f"uploads/orphan/verification_input/{organization.id}/{uuid.uuid4().hex}.bin",
        expected_sha256="a" * 64,
        size_bytes=1,
        expires_at=timezone.now() + timedelta(minutes=15),
    )
    verification = Verification.objects.create(
        organization=organization,
        upload_request=upload,
        requested_by=actor,
    )
    return organization, verification


def make_job(organization, verification, *, deadline_at=None, cancel_requested_at=None):
    return Job.objects.create(
        organization=organization,
        kind=JobKind.VERIFICATION,
        status=JobStatus.QUEUED,
        attempt=0,
        verification=verification,
        deadline_at=deadline_at or timezone.now() + timedelta(minutes=10),
        correlation_id=uuid.uuid4(),
        cancel_requested_at=cancel_requested_at,
    )


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_claim_moves_only_oldest_queued_job_to_processing(claim_context):
    organization, verification = claim_context
    older = make_job(organization, verification)
    newer = make_job(organization, verification)
    Job.objects.filter(pk=older.pk).update(created_at=timezone.now() - timedelta(minutes=1))

    claimed = claim_next_job()

    older.refresh_from_db()
    newer.refresh_from_db()
    assert claimed is not None and claimed.pk == older.pk
    assert older.status == JobStatus.PROCESSING
    assert newer.status == JobStatus.QUEUED


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_claim_never_processes_terminal_jobs(claim_context):
    organization, verification = claim_context
    terminal = make_job(organization, verification)
    terminal.status = JobStatus.SUCCEEDED
    terminal.save(update_fields=["status", "updated_at"])

    assert claim_next_job() is None

    terminal.refresh_from_db()
    assert terminal.status == JobStatus.SUCCEEDED


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_claim_cancels_requested_job_before_processing(claim_context):
    organization, verification = claim_context
    job = make_job(
        organization,
        verification,
        cancel_requested_at=timezone.now() - timedelta(seconds=1),
    )

    assert claim_next_job() is None

    job.refresh_from_db()
    assert job.status == JobStatus.CANCELLED
    assert job.safe_error_code is None


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_claim_rejects_expired_deadline_before_processing(claim_context):
    organization, verification = claim_context
    job = make_job(
        organization,
        verification,
        deadline_at=timezone.now() - timedelta(seconds=1),
    )

    assert claim_next_job() is None

    job.refresh_from_db()
    assert job.status == JobStatus.FAILED
    assert job.safe_error_code == "DEMO_JOB_DEADLINE_EXCEEDED"


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=False)
def test_claim_fails_closed_without_mutation_when_demo_mode_is_disabled(claim_context):
    organization, verification = claim_context
    job = make_job(organization, verification)

    assert claim_next_job() is None

    job.refresh_from_db()
    assert job.status == JobStatus.QUEUED


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_claim_selects_and_evaluates_candidate_inside_atomic_block(monkeypatch):
    observed = []
    atomic_depth = 0

    @contextmanager
    def observe_atomic():
        nonlocal atomic_depth
        atomic_depth += 1
        try:
            yield
        finally:
            atomic_depth -= 1

    class EmptyLockedQuery:
        def first(self):
            observed.append(("first", atomic_depth))
            return None

    def observe_lock(queryset):
        observed.append(("lock", atomic_depth))
        return EmptyLockedQuery()

    monkeypatch.setattr(demo_worker.transaction, "atomic", observe_atomic)
    monkeypatch.setattr(demo_worker, "_lock_jobs", observe_lock)

    assert claim_next_job() is None
    assert observed == [("lock", 1), ("first", 1)]


@pytest.mark.parametrize(
    ("supports_skip_locked", "expected_kwargs"),
    [(True, {"skip_locked": True}), (False, {})],
)
def test_lock_jobs_uses_skip_locked_only_when_database_advertises_support(
    monkeypatch,
    supports_skip_locked,
    expected_kwargs,
):
    calls = []

    class Query:
        def select_for_update(self, **kwargs):
            calls.append(kwargs)
            return self

    query = Query()
    monkeypatch.setattr(
        demo_worker.connection.features,
        "has_select_for_update_skip_locked",
        supports_skip_locked,
    )

    assert demo_worker._lock_jobs(query) is query
    assert calls == [expected_kwargs]
