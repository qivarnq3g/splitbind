import json
import uuid
from datetime import timedelta

import pytest
from django.test import Client, override_settings
from django.utils import timezone

from splitbind.access.models import Organization, Recipient, Role, User
from splitbind.documents.models import Verification
from splitbind.integrations.storage.fake import FakeObjectStorage
from splitbind.uploads.models import UploadPurpose, UploadRequest


SHA256 = "a" * 64


def csrf(client):
    client.get("/api/v1/auth/session")
    return {"HTTP_X_CSRFTOKEN": client.cookies["csrftoken"].value}


def login(client, user):
    client.force_login(user)
    return csrf(client)


def make_user(org, role, prefix):
    return User.objects.create_user(
        username=f"{prefix}-{uuid.uuid4().hex[:8]}", password="correct horse battery staple",
        organization=org, role=role,
    )


def ready_upload(org, actor, storage, purpose):
    upload_id = uuid.uuid4()
    key = f"uploads/orphan/{purpose}_input/{org.id}/{upload_id.hex}.bin"
    upload = UploadRequest.objects.create(
        id=upload_id, organization=org, requested_by=actor, purpose=purpose, object_key=key,
        expected_sha256=SHA256, size_bytes=1,
        expires_at=timezone.now() + timedelta(minutes=5), finalized_at=timezone.now(),
    )
    storage.inject_object(key=key, content_type="application/pdf", size_bytes=1, sha256=SHA256)
    return upload


@pytest.mark.django_db
def test_session_csrf_issuance_detail_job_and_cancel_routes_are_bounded():
    org = Organization.objects.create(name="API", slug=f"api-{uuid.uuid4().hex[:8]}")
    issuer = make_user(org, Role.ISSUER, "issuer")
    recipient = Recipient.objects.create(organization=org, external_reference="private-ref", display_name="Private Name")
    storage = FakeObjectStorage()
    upload = ready_upload(org, issuer, storage, UploadPurpose.ISSUANCE)
    client = Client(enforce_csrf_checks=True)
    headers = login(client, issuer)
    with override_settings(SPLITBIND_OBJECT_STORAGE=storage):
        created = client.post(
            "/api/v1/issuances",
            data=json.dumps({"recipient_id": str(recipient.id), "upload_id": str(upload.id), "correlation_id": str(uuid.uuid4())}),
            content_type="application/json", **headers,
        )
    assert created.status_code == 201
    assert set(created.json()) == {
        "id", "job_id", "status", "issued_at", "result_available", "algorithm_label",
    }
    assert created.json()["result_available"] is False
    assert created.json()["algorithm_label"] is None
    assert "private" not in created.content.decode().lower()
    issuance_id, job_id = created.json()["id"], created.json()["job_id"]
    detail = client.get(f"/api/v1/issuances/{issuance_id}")
    job = client.get(f"/api/v1/jobs/{job_id}")
    cancelled = client.post(
        f"/api/v1/jobs/{job_id}/cancel", data=json.dumps({"correlation_id": str(uuid.uuid4())}),
        content_type="application/json", **headers,
    )
    assert detail.status_code == job.status_code == 200
    assert "object_key" not in detail.content.decode() and "payload" not in job.content.decode()
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"


@pytest.mark.django_db
@pytest.mark.parametrize("role", [Role.VERIFIER, Role.AUDITOR])
def test_non_issuer_roles_cannot_create_issuance(role):
    org = Organization.objects.create(name="Role", slug=f"role-{uuid.uuid4().hex[:8]}")
    actor = make_user(org, role, "actor")
    client = Client(enforce_csrf_checks=True)
    headers = login(client, actor)
    response = client.post(
        "/api/v1/issuances", data=json.dumps({"recipient_id": str(uuid.uuid4()), "upload_id": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4())}),
        content_type="application/json", **headers,
    )
    assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("role", [Role.ISSUER, Role.AUDITOR])
def test_non_verifier_roles_cannot_create_verification(role):
    org = Organization.objects.create(name="Role", slug=f"role-{uuid.uuid4().hex[:8]}")
    actor = make_user(org, role, "actor")
    client = Client(enforce_csrf_checks=True)
    headers = login(client, actor)
    response = client.post(
        "/api/v1/verifications",
        data=json.dumps({"upload_id": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4())}),
        content_type="application/json",
        **headers,
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_foreign_recipient_and_upload_are_indistinguishable_404():
    own = Organization.objects.create(name="Own", slug=f"own-{uuid.uuid4().hex[:8]}")
    foreign = Organization.objects.create(name="Foreign", slug=f"foreign-{uuid.uuid4().hex[:8]}")
    issuer = make_user(own, Role.ISSUER, "issuer")
    foreign_user = make_user(foreign, Role.ISSUER, "foreign")
    recipient = Recipient.objects.create(organization=foreign, external_reference="secret", display_name="Secret")
    storage = FakeObjectStorage()
    upload = ready_upload(foreign, foreign_user, storage, UploadPurpose.ISSUANCE)
    client = Client(enforce_csrf_checks=True)
    headers = login(client, issuer)
    with override_settings(SPLITBIND_OBJECT_STORAGE=storage):
        response = client.post(
            "/api/v1/issuances", data=json.dumps({"recipient_id": str(recipient.id), "upload_id": str(upload.id), "correlation_id": str(uuid.uuid4())}),
            content_type="application/json", **headers,
        )
    assert response.status_code == 404
    assert "secret" not in response.content.decode().lower()


@pytest.mark.django_db
def test_verification_detail_projects_only_contract_evidence_and_metrics():
    org = Organization.objects.create(name="Evidence", slug=f"evidence-{uuid.uuid4().hex[:8]}")
    verifier = make_user(org, Role.VERIFIER, "verifier")
    storage = FakeObjectStorage()
    upload = ready_upload(org, verifier, storage, UploadPurpose.VERIFICATION)
    verification = Verification.objects.create(
        organization=org,
        upload_request=upload,
        requested_by=verifier,
        evidence={
            "fingerprint_confidence": 0.75,
            "limitations": ["geometry.limited"],
            "input_object_key": "inputs/verification/private.bin",
            "recipient_display_name": "Private Person",
        },
        metrics={
            "processing_ms": 25,
            "exception_text": "https://provider.invalid/private?secret=yes",
        },
    )
    client = Client()
    client.force_login(verifier)

    response = client.get(f"/api/v1/verifications/{verification.id}")

    assert response.status_code == 200
    assert response.json()["evidence"] == {
        "fingerprint_confidence": 0.75,
        "limitations": ["geometry.limited"],
    }
    assert response.json()["metrics"] == {"processing_ms": 25}
    serialized = response.content.decode().lower()
    for forbidden in ("object_key", "private person", "provider.invalid", "exception_text"):
        assert forbidden not in serialized
