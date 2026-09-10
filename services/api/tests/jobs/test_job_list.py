import json
import uuid
from datetime import timedelta

import pytest
from django.test import Client, override_settings
from django.utils import timezone

from splitbind.access.models import Organization, Recipient, Role, User
from splitbind.documents.models import Document, Issuance, Verification, VerificationStatus
from splitbind.integrations.storage.fake import FakeObjectStorage
from splitbind.jobs.models import Job, JobKind, JobStatus
from splitbind.uploads.models import UploadPurpose, UploadRequest


SHA256 = "b" * 64


def make_user(org, role, prefix):
    return User.objects.create_user(
        username=f"{prefix}-{uuid.uuid4().hex[:8]}",
        password="correct horse battery staple",
        organization=org,
        role=role,
    )


def ready_upload(org, actor, storage, purpose):
    upload_id = uuid.uuid4()
    key = f"uploads/orphan/{purpose}_input/{org.id}/{upload_id.hex}.bin"
    upload = UploadRequest.objects.create(
        id=upload_id,
        organization=org,
        requested_by=actor,
        purpose=purpose,
        object_key=key,
        expected_sha256=SHA256,
        size_bytes=100,
        expires_at=timezone.now() + timedelta(minutes=5),
        finalized_at=timezone.now(),
    )
    storage.inject_object(key=key, content_type="application/pdf", size_bytes=100, sha256=SHA256)
    return upload


@pytest.mark.django_db
def test_job_list_unauthenticated_denied():
    client = Client()
    response = client.get("/api/v1/jobs")
    assert response.status_code in {401, 403}


@pytest.mark.django_db
def test_job_list_issuer_scopes_to_own_issuances():
    org = Organization.objects.create(name="JobListOrg", slug=f"job-list-{uuid.uuid4().hex[:8]}")
    other_org = Organization.objects.create(name="OtherOrg", slug=f"other-org-{uuid.uuid4().hex[:8]}")

    issuer1 = make_user(org, Role.ISSUER, "issuer1")
    issuer2 = make_user(org, Role.ISSUER, "issuer2")
    foreign_user = make_user(other_org, Role.ISSUER, "foreign")

    storage = FakeObjectStorage()
    u1 = ready_upload(org, issuer1, storage, UploadPurpose.ISSUANCE)
    doc1 = Document.objects.create(
        organization=org,
        created_by=issuer1,
        upload_request=u1,
        source_object_key="src1",
        expected_source_sha256=SHA256,
    )
    r1 = Recipient.objects.create(
        organization=org,
        external_reference="recipient1@example.com",
        display_name="Nguyen Van A",
    )
    iss1 = Issuance.objects.create(
        organization=org,
        document=doc1,
        recipient=r1,
        created_by=issuer1,
    )
    job1 = Job.objects.create(
        organization=org,
        kind=JobKind.ISSUANCE,
        status=JobStatus.SUCCEEDED,
        issuance=iss1,
        deadline_at=timezone.now() + timedelta(minutes=5),
        correlation_id=uuid.uuid4(),
    )

    # Job from issuer2
    u2 = ready_upload(org, issuer2, storage, UploadPurpose.ISSUANCE)
    doc2 = Document.objects.create(
        organization=org,
        created_by=issuer2,
        upload_request=u2,
        source_object_key="src2",
        expected_source_sha256=SHA256,
    )
    r2 = Recipient.objects.create(
        organization=org,
        external_reference="recipient2@example.com",
        display_name="Tran Thi B",
    )
    iss2 = Issuance.objects.create(
        organization=org,
        document=doc2,
        recipient=r2,
        created_by=issuer2,
    )
    Job.objects.create(
        organization=org,
        kind=JobKind.ISSUANCE,
        status=JobStatus.SUCCEEDED,
        issuance=iss2,
        deadline_at=timezone.now() + timedelta(minutes=5),
        correlation_id=uuid.uuid4(),
    )

    client = Client()
    client.force_login(issuer1)

    response = client.get("/api/v1/jobs")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == str(job1.id)
    assert data[0]["kind"] == "issuance"
    assert data[0]["issuance_id"] == str(iss1.id)
    assert data[0]["recipient_email"] == "recipient1@example.com"
    assert data[0]["recipient_name"] == "Nguyen Van A"


@pytest.mark.django_db
def test_job_list_verifier_scopes_to_own_verifications():
    org = Organization.objects.create(name="VerifyOrg", slug=f"verify-org-{uuid.uuid4().hex[:8]}")
    verifier = make_user(org, Role.VERIFIER, "verifier")
    admin = make_user(org, Role.ADMINISTRATOR, "admin")

    storage = FakeObjectStorage()
    u = ready_upload(org, verifier, storage, UploadPurpose.VERIFICATION)
    v = Verification.objects.create(
        organization=org,
        upload_request=u,
        requested_by=verifier,
        status=VerificationStatus.VERIFIED_INTACT,
    )
    job = Job.objects.create(
        organization=org,
        kind=JobKind.VERIFICATION,
        status=JobStatus.SUCCEEDED,
        verification=v,
        deadline_at=timezone.now() + timedelta(minutes=5),
        correlation_id=uuid.uuid4(),
    )

    client = Client()
    client.force_login(verifier)

    response = client.get("/api/v1/jobs")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == str(job.id)
    assert data[0]["kind"] == "verification"
    assert data[0]["verification_id"] == str(v.id)
    assert data[0]["verification_status"] == "VERIFIED_INTACT"

    # Admin can also see this job
    client.force_login(admin)
    admin_response = client.get("/api/v1/jobs")
    assert admin_response.status_code == 200
    assert any(j["id"] == str(job.id) for j in admin_response.json())


@pytest.mark.django_db
def test_job_list_filter_by_kind():
    org = Organization.objects.create(name="KindOrg", slug=f"kind-org-{uuid.uuid4().hex[:8]}")
    admin = make_user(org, Role.ADMINISTRATOR, "admin")

    storage = FakeObjectStorage()
    # Issuance job
    u1 = ready_upload(org, admin, storage, UploadPurpose.ISSUANCE)
    doc = Document.objects.create(
        organization=org,
        created_by=admin,
        upload_request=u1,
        source_object_key="doc-kind",
        expected_source_sha256=SHA256,
    )
    r = Recipient.objects.create(organization=org, external_reference="kind@example.com", display_name="Kind")
    iss = Issuance.objects.create(organization=org, document=doc, recipient=r, created_by=admin)
    job_iss = Job.objects.create(
        organization=org,
        kind=JobKind.ISSUANCE,
        status=JobStatus.SUCCEEDED,
        issuance=iss,
        deadline_at=timezone.now() + timedelta(minutes=5),
        correlation_id=uuid.uuid4(),
    )

    # Verification job
    u2 = ready_upload(org, admin, storage, UploadPurpose.VERIFICATION)
    v = Verification.objects.create(organization=org, upload_request=u2, requested_by=admin)
    job_v = Job.objects.create(
        organization=org,
        kind=JobKind.VERIFICATION,
        status=JobStatus.SUCCEEDED,
        verification=v,
        deadline_at=timezone.now() + timedelta(minutes=5),
        correlation_id=uuid.uuid4(),
    )

    client = Client()
    client.force_login(admin)

    resp_iss = client.get("/api/v1/jobs?kind=issuance")
    assert resp_iss.status_code == 200
    assert len(resp_iss.json()) == 1
    assert resp_iss.json()[0]["id"] == str(job_iss.id)

    resp_ver = client.get("/api/v1/jobs?kind=verification")
    assert resp_ver.status_code == 200
    assert len(resp_ver.json()) == 1
    assert resp_ver.json()[0]["id"] == str(job_v.id)
