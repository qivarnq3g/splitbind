import json
import uuid
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.test import Client, override_settings
from django.utils import timezone

from splitbind.access.models import Organization, Role
from splitbind.audit.models import AuditEvent, AuditOutcome
from splitbind.integrations.storage.fake import FakeObjectStorage
from splitbind.integrations.storage.s3 import S3ObjectStorage
from splitbind.uploads.models import UploadPurpose, UploadRequest
from splitbind.uploads.services import MAX_UPLOAD_BYTES, UploadRejected, create_upload


SHA256 = "a" * 64


def create_user(organization, role, suffix):
    return get_user_model().objects.create_user(
        username=f"upload-{role}-{suffix}",
        password="test-password-not-a-secret",
        organization=organization,
        role=role,
    )


def csrf_headers(client):
    return {"HTTP_X_CSRFTOKEN": client.get("/api/v1/auth/session").json()["csrf_token"]}


def upload_payload(kind="issuance_input", **overrides):
    payload = {
        "kind": kind,
        "filename": "../../report.pdf",
        "content_type": "application/pdf",
        "size_bytes": 1024,
        "sha256": SHA256,
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def storage():
    return FakeObjectStorage()


@pytest.fixture
def organization(db):
    return Organization.objects.create(name="Upload Organization", slug="upload-org")


@pytest.fixture
def actors(organization):
    return {
        role: create_user(organization, role, role)
        for role in Role.values
    }


@pytest.fixture
def browser_client(storage):
    with override_settings(SPLITBIND_OBJECT_STORAGE=storage):
        client = Client(enforce_csrf_checks=True)
        yield client


def login(client, user):
    assert client.login(username=user.username, password="test-password-not-a-secret")


@pytest.mark.django_db
def test_upload_intent_uses_generated_key_short_ttl_and_never_persists_url(browser_client, actors):
    login(browser_client, actors[Role.ISSUER])
    response = browser_client.post(
        "/api/v1/uploads",
        data=json.dumps(upload_payload()),
        content_type="application/json",
        **csrf_headers(browser_client),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["object_key"].startswith(
        f"uploads/orphan/issuance_input/{actors[Role.ISSUER].organization_id}/"
    )
    assert payload["object_key"].endswith(".bin")
    assert "report.pdf" not in payload["object_key"]
    assert timezone.datetime.fromisoformat(payload["expires_at"].replace("Z", "+00:00")) <= timezone.now() + timedelta(minutes=15)
    assert payload["required_headers"] == {
        "Content-Length": "1024",
        "Content-Type": "application/pdf",
        "x-amz-meta-sha256": SHA256,
    }
    record = UploadRequest.objects.get(pk=payload["id"])
    assert record.sha256 == SHA256
    assert record.size_bytes == 1024
    assert payload["upload_url"] not in str(record.__dict__)
    assert payload["upload_url"] not in str(AuditEvent.objects.get(action="upload.intent.created").metadata)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("role", "kind", "expected"),
    [
        (Role.ISSUER, "issuance_input", 201),
        (Role.ISSUER, "verification_input", 403),
        (Role.VERIFIER, "verification_input", 201),
        (Role.VERIFIER, "issuance_input", 403),
        (Role.ADMINISTRATOR, "issuance_input", 201),
        (Role.ADMINISTRATOR, "verification_input", 201),
        (Role.AUDITOR, "issuance_input", 403),
    ],
)
def test_upload_role_matrix_and_denials_are_audited(browser_client, actors, role, kind, expected):
    login(browser_client, actors[role])
    content_type = "image/png" if kind == "verification_input" else "application/pdf"

    response = browser_client.post(
        "/api/v1/uploads",
        data=json.dumps(upload_payload(kind, content_type=content_type)),
        content_type="application/json",
        **csrf_headers(browser_client),
    )

    assert response.status_code == expected
    event = AuditEvent.objects.order_by("-created_at").first()
    assert event.actor_id == actors[role].id
    assert event.outcome == (AuditOutcome.SUCCEEDED if expected == 201 else AuditOutcome.DENIED)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "payload",
    [
        upload_payload(size_bytes=0),
        upload_payload(size_bytes=MAX_UPLOAD_BYTES + 1),
        upload_payload(sha256="A" * 64),
        upload_payload(sha256="short"),
        upload_payload(content_type="image/png"),
        upload_payload("unknown_input"),
    ],
)
def test_upload_intent_rejects_invalid_boundaries(browser_client, actors, payload):
    login(browser_client, actors[Role.ISSUER])
    response = browser_client.post(
        "/api/v1/uploads",
        data=json.dumps(payload),
        content_type="application/json",
        **csrf_headers(browser_client),
    )
    assert response.status_code == 400
    assert UploadRequest.objects.count() == 0


@pytest.mark.django_db
def test_upload_mutation_requires_session_and_csrf(browser_client, actors):
    assert browser_client.post("/api/v1/uploads", data=json.dumps(upload_payload()), content_type="application/json").status_code == 403
    login(browser_client, actors[Role.ISSUER])
    assert browser_client.post("/api/v1/uploads", data=json.dumps(upload_payload()), content_type="application/json").status_code == 403


@pytest.mark.django_db
def test_complete_checks_observed_metadata_and_is_idempotent(browser_client, actors, storage):
    login(browser_client, actors[Role.ISSUER])
    created = browser_client.post(
        "/api/v1/uploads", data=json.dumps(upload_payload()), content_type="application/json", **csrf_headers(browser_client)
    ).json()
    storage.put_object(
        key=created["object_key"], content_type="application/pdf", size_bytes=1024, sha256=SHA256
    )

    completed = browser_client.post(
        f"/api/v1/uploads/{created['id']}/complete",
        data=json.dumps({"sha256": SHA256}),
        content_type="application/json",
        **csrf_headers(browser_client),
    )
    replay = browser_client.post(
        f"/api/v1/uploads/{created['id']}/complete",
        data=json.dumps({"sha256": SHA256}),
        content_type="application/json",
        **csrf_headers(browser_client),
    )

    assert completed.status_code == replay.status_code == 200
    assert completed.json()["finalized_at"] == replay.json()["finalized_at"]
    assert UploadRequest.objects.get(pk=created["id"]).finalized_at is not None
    assert AuditEvent.objects.filter(action="upload.completed", outcome=AuditOutcome.SUCCEEDED).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("state", ["missing", "size", "checksum", "expired"])
def test_complete_rejects_missing_expired_or_mismatched_object(browser_client, actors, storage, state, monkeypatch):
    login(browser_client, actors[Role.ISSUER])
    created = browser_client.post(
        "/api/v1/uploads", data=json.dumps(upload_payload()), content_type="application/json", **csrf_headers(browser_client)
    ).json()
    if state == "size":
        storage.inject_object(key=created["object_key"], content_type="application/pdf", size_bytes=1023, sha256=SHA256)
    elif state == "checksum":
        storage.inject_object(key=created["object_key"], content_type="application/pdf", size_bytes=1024, sha256="b" * 64)
    elif state == "expired":
        storage.put_object(key=created["object_key"], content_type="application/pdf", size_bytes=1024, sha256=SHA256)
        future = timezone.now() + timedelta(minutes=16)
        monkeypatch.setattr("splitbind.uploads.services.timezone.now", lambda: future)

    response = browser_client.post(
        f"/api/v1/uploads/{created['id']}/complete",
        data=json.dumps({"sha256": SHA256}), content_type="application/json", **csrf_headers(browser_client)
    )
    assert response.status_code == 400
    assert response.json()["code"].startswith("UPLOAD_")
    assert UploadRequest.objects.get(pk=created["id"]).finalized_at is None


@pytest.mark.django_db
def test_complete_foreign_upload_returns_404_and_does_not_reveal_identity(storage):
    first_org = Organization.objects.create(name="First", slug="first-upload-org")
    foreign_org = Organization.objects.create(name="Foreign", slug="foreign-upload-org")
    issuer = create_user(first_org, Role.ISSUER, "first")
    foreign = create_user(foreign_org, Role.ISSUER, "foreign")
    with override_settings(SPLITBIND_OBJECT_STORAGE=storage):
        foreign_upload = create_upload(
            foreign, kind="issuance_input", filename="x.pdf", content_type="application/pdf", size_bytes=1, sha256=SHA256
        )
        client = Client(enforce_csrf_checks=True)
        login(client, issuer)
        response = client.post(
            f"/api/v1/uploads/{foreign_upload.record.id}/complete",
            data=json.dumps({"sha256": SHA256}), content_type="application/json", **csrf_headers(client)
        )
    assert response.status_code == 404
    assert str(foreign_upload.record.id) not in response.content.decode()


@pytest.mark.django_db
def test_provider_failure_returns_safe_code_and_audit_never_contains_provider_details(browser_client, actors, storage):
    storage.fail_next("presign_put", "https://provider.example.test/secret?token=not-retained")
    login(browser_client, actors[Role.ISSUER])

    response = browser_client.post(
        "/api/v1/uploads", data=json.dumps(upload_payload()), content_type="application/json", **csrf_headers(browser_client)
    )

    assert response.status_code == 503
    assert response.json() == {"code": "STORAGE_UNAVAILABLE"}
    assert "provider.example.test" not in str(AuditEvent.objects.latest("created_at").metadata)


@pytest.mark.django_db
def test_upload_intent_identity_is_immutable_on_instance_and_queryset_updates(organization, actors):
    record = UploadRequest.objects.create(
        organization=organization,
        requested_by=actors[Role.ISSUER],
        purpose=UploadPurpose.ISSUANCE,
        object_key=f"uploads/orphan/issuance_input/{organization.id}/{uuid.uuid4().hex}.bin",
        sha256=SHA256,
        size_bytes=1,
        expires_at=timezone.now() + timedelta(minutes=15),
    )
    record.sha256 = "b" * 64
    with pytest.raises(ValueError, match="immutable"):
        record.save()
    with pytest.raises(ValueError, match="immutable"):
        UploadRequest.objects.filter(pk=record.pk).update(size_bytes=2)


def test_fake_storage_enforces_controlled_keys_headers_expiry_and_copy_cleanup():
    storage = FakeObjectStorage()
    source = f"uploads/orphan/issuance_input/{uuid.uuid4()}/{uuid.uuid4().hex}.bin"
    destination = f"uploads/orphan/verification_input/{uuid.uuid4()}/{uuid.uuid4().hex}.bin"
    signed = storage.presign_put(
        key=source, content_type="application/pdf", size_bytes=1, sha256=SHA256, expires=timedelta(minutes=15)
    )
    assert signed.headers["x-amz-meta-sha256"] == SHA256
    storage.put_object(key=source, content_type="application/pdf", size_bytes=1, sha256=SHA256)
    copied = storage.copy_verified(source=source, destination=destination, sha256=SHA256)
    assert copied.key == destination
    assert storage.head(key=destination).sha256 == SHA256
    storage.delete(key=destination)
    assert storage.head(key=destination) is None
    with pytest.raises(ValueError, match="controlled"):
        storage.presign_get(key="uploads/orphan/../secret", expires=timedelta(minutes=1))


def test_fake_storage_rejects_invalid_copy_without_leaving_destination():
    storage = FakeObjectStorage()
    source = f"uploads/orphan/issuance_input/{uuid.uuid4()}/{uuid.uuid4().hex}.bin"
    destination = f"uploads/orphan/issuance_input/{uuid.uuid4()}/{uuid.uuid4().hex}.bin"
    storage.put_object(key=source, content_type="application/pdf", size_bytes=1, sha256=SHA256)
    with pytest.raises(UploadRejected, match="STORAGE_COPY_MISMATCH"):
        storage.copy_verified(source=source, destination=destination, sha256="b" * 64)
    assert storage.head(key=destination) is None


@override_settings(
    SPLITBIND_STORAGE_ENDPOINT="",
    SPLITBIND_STORAGE_BUCKET="",
    SPLITBIND_STORAGE_ACCESS_KEY_ID="",
    SPLITBIND_STORAGE_SECRET_ACCESS_KEY="",
)
def test_s3_configuration_fails_closed_when_any_required_environment_setting_is_absent():
    with pytest.raises(ImproperlyConfigured, match="R2 storage endpoint, bucket, and credentials"):
        S3ObjectStorage.from_settings()
