import uuid
from datetime import timedelta

import pytest
from django.test import Client, override_settings
from django.utils import timezone

from splitbind.access.models import Organization, Recipient, Role, User
from splitbind.audit.models import AuditEvent, AuditOutcome
from splitbind.demo.capabilities import DEMO_ALGORITHM_LABEL
from splitbind.demo.models import (
    DEMO_CANONICAL_CANVAS,
    DEMO_FROZEN_CANDIDATE_IDENTIFIER,
    DEMO_LIMITATIONS,
    DemoIssuanceResult,
    DemoOutputState,
    _allow_demo_result_write,
)
from splitbind.documents.models import Document, Issuance
from splitbind.integrations.storage.fake import FakeObjectStorage
from splitbind.jobs.models import Job, JobKind, JobStatus
from splitbind.retention.capabilities import _allow_deletion_evidence_write
from splitbind.uploads.models import UploadPurpose, UploadRequest


SHA256 = "a" * 64
OUTPUT_SHA256 = "b" * 64
PASSWORD = "test-password-not-a-secret"


class RecordingStorage(FakeObjectStorage):
    def __init__(self):
        super().__init__()
        self.presign_get_expiry = None

    def presign_get(self, *, key, expires):
        self.presign_get_expiry = expires
        return super().presign_get(key=key, expires=expires)


def make_user(organization, role, suffix):
    return User.objects.create_user(
        username=f"{role}-{suffix}-{uuid.uuid4().hex[:8]}",
        password=PASSWORD,
        organization=organization,
        role=role,
    )


def make_issuance(organization, actor, suffix):
    upload = UploadRequest.objects.create(
        organization=organization,
        requested_by=actor,
        purpose=UploadPurpose.ISSUANCE,
        object_key=(
            f"uploads/orphan/issuance_input/{organization.id}/"
            f"{uuid.uuid4().hex}.bin"
        ),
        expected_sha256=SHA256,
        size_bytes=100,
        expires_at=timezone.now() + timedelta(minutes=15),
    )
    document = Document.objects.create(
        organization=organization,
        created_by=actor,
        upload_request=upload,
        source_object_key=f"inputs/issuance/{organization.id}/{upload.id}.bin",
        expected_source_sha256=SHA256,
        page_count=1,
    )
    recipient = Recipient.objects.create(
        organization=organization,
        external_reference=f"recipient-{suffix}-{uuid.uuid4().hex[:8]}",
        display_name="Synthetic Recipient",
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
        status=JobStatus.SUCCEEDED,
        issuance=issuance,
        deadline_at=timezone.now() + timedelta(minutes=10),
        correlation_id=uuid.uuid4(),
    )
    return issuance, job


def commit_result(issuance, job):
    output_key = f"outputs/issuance/{issuance.organization_id}/{issuance.id}.pdf"
    issuance.output_object_key = output_key
    issuance.output_sha256 = OUTPUT_SHA256
    issuance.save(update_fields=["output_object_key", "output_sha256"])
    with _allow_demo_result_write():
        return DemoIssuanceResult.objects.create(
            organization_id=issuance.organization_id,
            job=job,
            issuance=issuance,
            attempt=job.attempt,
            owner_token=uuid.uuid4(),
            output_object_key=output_key,
            output_state=DemoOutputState.COMMITTED,
            algorithm_label=DEMO_ALGORITHM_LABEL,
            candidate_identifier=DEMO_FROZEN_CANDIDATE_IDENTIFIER,
            canvas_height=DEMO_CANONICAL_CANVAS[0],
            canvas_width=DEMO_CANONICAL_CANVAS[1],
            input_sha256=SHA256,
            output_sha256=OUTPUT_SHA256,
            page_count=1,
            processing_ms=10,
            limitations=list(DEMO_LIMITATIONS),
        )


@pytest.fixture
def issuance_context(db):
    organization = Organization.objects.create(name="Download", slug=f"download-{uuid.uuid4().hex[:8]}")
    issuer = make_user(organization, Role.ISSUER, "owner")
    issuance, job = make_issuance(organization, issuer, "owned")
    storage = RecordingStorage()
    return organization, issuer, issuance, job, storage


def login(client, user):
    assert client.login(username=user.username, password=PASSWORD)


def assert_private_no_store(response):
    directives = {item.strip() for item in response.headers["Cache-Control"].split(",")}
    assert {"private", "no-store"} <= directives


@pytest.mark.django_db
def test_issuance_payload_reports_only_consistent_committed_result(issuance_context):
    _organization, issuer, issuance, job, _storage = issuance_context
    client = Client()
    login(client, issuer)

    processing = client.get(f"/api/v1/issuances/{issuance.id}")
    assert processing.status_code == 200
    assert processing.json()["result_available"] is False
    assert processing.json()["algorithm_label"] is None

    commit_result(issuance, job)
    available = client.get(f"/api/v1/issuances/{issuance.id}")
    assert available.status_code == 200
    assert available.json()["result_available"] is True
    assert available.json()["algorithm_label"] == DEMO_ALGORITHM_LABEL


@pytest.mark.django_db
def test_issuance_result_download_requires_authentication(issuance_context):
    _organization, _issuer, issuance, _job, _storage = issuance_context
    response = Client().get(f"/api/v1/issuances/{issuance.id}/result")
    assert response.status_code == 403
    assert_private_no_store(response)


@pytest.mark.django_db
def test_issuer_owner_may_download_committed_result_and_grant_is_audited(issuance_context):
    _organization, issuer, issuance, job, storage = issuance_context
    commit_result(issuance, job)
    client = Client()
    login(client, issuer)

    with override_settings(SPLITBIND_OBJECT_STORAGE=storage):
        response = client.get(f"/api/v1/issuances/{issuance.id}/result")

    assert response.status_code == 200
    assert_private_no_store(response)
    event = AuditEvent.objects.get(action="issuance.result_download_granted")
    assert event.actor_id == issuer.id
    assert event.target_id == str(issuance.id)
    assert event.outcome == AuditOutcome.SUCCEEDED
    assert event.metadata == {"attempt": "0"}
    serialized = str(event.metadata).lower()
    assert "http" not in serialized and "output" not in serialized and "signed" not in serialized


@pytest.mark.django_db
@pytest.mark.parametrize("role", [Role.ADMINISTRATOR, Role.AUDITOR])
def test_same_organization_read_roles_may_download_committed_result(issuance_context, role):
    organization, _issuer, issuance, job, storage = issuance_context
    commit_result(issuance, job)
    actor = make_user(organization, role, "reader")
    client = Client()
    login(client, actor)

    before = timezone.now()
    with override_settings(SPLITBIND_OBJECT_STORAGE=storage):
        response = client.get(f"/api/v1/issuances/{issuance.id}/result")
    after = timezone.now()

    assert response.status_code == 200
    payload = response.json()
    assert payload["download_url"].startswith("https://fake-storage.invalid/")
    assert storage.presign_get_expiry == timedelta(minutes=5)
    expires_at = timezone.datetime.fromisoformat(payload["expires_at"])
    assert before + timedelta(minutes=5) <= expires_at <= after + timedelta(minutes=5)
    assert "output_object_key" not in payload
    assert_private_no_store(response)


@pytest.mark.django_db
def test_issuance_result_download_is_requester_and_organization_scoped(issuance_context):
    organization, _issuer, issuance, job, storage = issuance_context
    commit_result(issuance, job)
    other_issuer = make_user(organization, Role.ISSUER, "other")
    foreign_org = Organization.objects.create(name="Foreign", slug=f"foreign-{uuid.uuid4().hex[:8]}")
    foreign_admin = make_user(foreign_org, Role.ADMINISTRATOR, "foreign")

    for actor in (other_issuer, foreign_admin):
        client = Client()
        login(client, actor)
        with override_settings(SPLITBIND_OBJECT_STORAGE=storage):
            response = client.get(f"/api/v1/issuances/{issuance.id}/result")
        assert response.status_code == 404
        assert_private_no_store(response)
        event = AuditEvent.objects.get(
            organization_id=actor.organization_id,
            actor_id=actor.id,
            action="issuance.result_download_denied",
        )
        assert event.target_id == str(actor.id)
        assert event.outcome == AuditOutcome.DENIED
        assert event.metadata == {"safe_error_code": "WORKFLOW_NOT_FOUND"}


@pytest.mark.django_db
def test_issuance_result_download_returns_stable_conflict_when_unavailable(issuance_context):
    _organization, issuer, issuance, _job, storage = issuance_context
    client = Client()
    login(client, issuer)
    with override_settings(SPLITBIND_OBJECT_STORAGE=storage):
        response = client.get(f"/api/v1/issuances/{issuance.id}/result")
    assert response.status_code == 409
    assert response.json() == {"code": "ISSUANCE_RESULT_UNAVAILABLE"}
    assert_private_no_store(response)
    event = AuditEvent.objects.get(action="issuance.result_download_denied")
    assert event.target_id == str(issuance.id)
    assert event.outcome == AuditOutcome.DENIED
    assert event.metadata == {"safe_error_code": "ISSUANCE_RESULT_UNAVAILABLE"}


@pytest.mark.django_db
def test_issuance_result_download_rejects_deleted_output(issuance_context):
    _organization, issuer, issuance, job, storage = issuance_context
    commit_result(issuance, job)
    issuance.output_deleted_at = timezone.now()
    with _allow_deletion_evidence_write():
        issuance.save(update_fields=["output_deleted_at"])
    client = Client()
    login(client, issuer)
    with override_settings(SPLITBIND_OBJECT_STORAGE=storage):
        response = client.get(f"/api/v1/issuances/{issuance.id}/result")
    assert response.status_code == 409
    assert response.json() == {"code": "ISSUANCE_RESULT_UNAVAILABLE"}
    assert_private_no_store(response)


@pytest.mark.django_db
def test_issuance_result_download_rejects_inconsistent_output_metadata(issuance_context):
    _organization, issuer, issuance, job, storage = issuance_context
    commit_result(issuance, job)
    Issuance.objects.filter(pk=issuance.pk).update(output_sha256=SHA256)
    client = Client()
    login(client, issuer)
    with override_settings(SPLITBIND_OBJECT_STORAGE=storage):
        response = client.get(f"/api/v1/issuances/{issuance.id}/result")
    assert response.status_code == 409
    assert response.json() == {"code": "ISSUANCE_RESULT_UNAVAILABLE"}
    assert_private_no_store(response)


@pytest.mark.django_db
def test_issuance_result_download_rejects_committed_evidence_from_a_stale_attempt(issuance_context):
    _organization, issuer, issuance, job, storage = issuance_context
    commit_result(issuance, job)
    Job.objects.filter(pk=job.pk).update(attempt=1)
    client = Client()
    login(client, issuer)

    detail = client.get(f"/api/v1/issuances/{issuance.id}")
    with override_settings(SPLITBIND_OBJECT_STORAGE=storage):
        response = client.get(f"/api/v1/issuances/{issuance.id}/result")

    assert detail.json()["result_available"] is False
    assert detail.json()["algorithm_label"] is None
    assert response.status_code == 409
    assert response.json() == {"code": "ISSUANCE_RESULT_UNAVAILABLE"}
    assert storage.presign_get_expiry is None
    assert_private_no_store(response)


@pytest.mark.django_db
def test_issuance_result_download_hides_storage_failure(issuance_context):
    _organization, issuer, issuance, job, storage = issuance_context
    commit_result(issuance, job)
    storage.fail_next("presign_get", "private provider detail")
    client = Client()
    login(client, issuer)
    with override_settings(SPLITBIND_OBJECT_STORAGE=storage):
        response = client.get(f"/api/v1/issuances/{issuance.id}/result")
    assert response.status_code == 503
    assert response.json() == {"code": "STORAGE_UNAVAILABLE"}
    assert "private" not in response.content.decode().lower()
    assert_private_no_store(response)
    event = AuditEvent.objects.get(action="issuance.result_download_failed")
    assert event.target_id == str(issuance.id)
    assert event.outcome == AuditOutcome.FAILED
    assert event.metadata == {"safe_error_code": "STORAGE_UNAVAILABLE"}
