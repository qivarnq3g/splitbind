import uuid
from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from splitbind.access.models import Organization, Role, User
from splitbind.audit.models import AuditEvent
from splitbind.documents.models import Verification
from splitbind.jobs.models import Job, JobKind, JobStatus
from splitbind.jobs.services import JobConflict, request_cancel
from splitbind.jobs.state import transition_job
from splitbind.uploads.models import UploadPurpose, UploadRequest


@pytest.fixture
def cancel_context(db):
    org = Organization.objects.create(name="Cancel", slug=f"cancel-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(username=f"v-{uuid.uuid4().hex[:8]}", password="correct horse battery staple", organization=org, role=Role.VERIFIER)
    upload = UploadRequest.objects.create(
        organization=org, requested_by=actor, purpose=UploadPurpose.VERIFICATION,
        object_key=f"uploads/orphan/verification_input/{org.id}/{uuid.uuid4().hex}.bin",
        expected_sha256="a" * 64, size_bytes=1, expires_at=timezone.now() + timedelta(minutes=5),
    )
    verification = Verification.objects.create(organization=org, upload_request=upload, requested_by=actor)
    return org, actor, verification


def make_job(org, verification, status):
    return Job.objects.create(
        organization=org, kind=JobKind.VERIFICATION, status=status, attempt=0,
        verification=verification, deadline_at=timezone.now() + timedelta(minutes=10), correlation_id=uuid.uuid4(),
    )


@pytest.mark.django_db
@pytest.mark.parametrize("status", [JobStatus.CREATED, JobStatus.QUEUED, JobStatus.RETRYABLE_FAILED])
def test_cancel_nonprocessing_cancellable_state_is_atomic_and_idempotent(cancel_context, status):
    org, actor, verification = cancel_context
    job = make_job(org, verification, status)
    correlation = uuid.uuid4()
    request_cancel(actor, job.id, correlation)
    request_cancel(actor, job.id, correlation)
    job.refresh_from_db()
    assert job.status == JobStatus.CANCELLED and job.cancel_requested_at is not None
    assert AuditEvent.objects.filter(action="job.cancel_requested", target_id=str(job.id)).count() == 1


@pytest.mark.django_db
def test_processing_cancel_sets_request_without_illegal_transition(cancel_context):
    org, actor, verification = cancel_context
    job = make_job(org, verification, JobStatus.PROCESSING)
    request_cancel(actor, job.id, uuid.uuid4())
    job.refresh_from_db()
    assert job.status == JobStatus.PROCESSING and job.cancel_requested_at is not None

    transition_job(job, JobStatus.CANCELLED)
    job.save(update_fields=["status", "updated_at"])
    job.refresh_from_db()
    assert job.status == JobStatus.CANCELLED


@pytest.mark.django_db
def test_terminal_non_cancelled_job_returns_stable_conflict(cancel_context):
    org, actor, verification = cancel_context
    job = make_job(org, verification, JobStatus.SUCCEEDED)
    with pytest.raises(JobConflict, match="JOB_TERMINAL"):
        request_cancel(actor, job.id, uuid.uuid4())


@pytest.mark.django_db
def test_auditor_remains_read_only_when_job_is_visible(cancel_context):
    org, _, verification = cancel_context
    auditor = User.objects.create_user(
        username=f"auditor-{uuid.uuid4().hex[:8]}",
        password="correct horse battery staple",
        organization=org,
        role=Role.AUDITOR,
    )
    job = make_job(org, verification, JobStatus.CREATED)

    with pytest.raises(PermissionDenied, match="WORKFLOW_FORBIDDEN"):
        request_cancel(auditor, job.id, uuid.uuid4())

    job.refresh_from_db()
    assert job.status == JobStatus.CREATED
    assert job.cancel_requested_at is None


@pytest.mark.django_db
def test_cancel_replay_requires_the_same_actor_and_correlation(cancel_context):
    org, actor, verification = cancel_context
    job = make_job(org, verification, JobStatus.CREATED)
    request_cancel(actor, job.id, uuid.uuid4())

    with pytest.raises(JobConflict, match="JOB_CANCEL_ALREADY_REQUESTED"):
        request_cancel(actor, job.id, uuid.uuid4())

    assert AuditEvent.objects.filter(
        action="job.cancel_requested", target_id=str(job.id),
    ).count() == 1
