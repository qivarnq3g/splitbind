import json
import sys
import threading
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import close_old_connections, connection
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TransactionTestCase, override_settings
from django.utils import timezone

from splitbind.access.models import Organization, Role
from splitbind.audit.models import AuditEvent, AuditOutcome
from splitbind.integrations.storage.fake import FakeObjectStorage
from splitbind.integrations.storage.s3 import S3ObjectStorage
from splitbind.uploads.models import UploadPurpose, UploadRequest
from splitbind.uploads.services import MAX_UPLOAD_BYTES, UploadRejected, complete_upload, create_upload


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
    assert record.expected_sha256 == SHA256
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
    event = AuditEvent.objects.latest("created_at")
    assert event.action == "upload.complete.denied"
    assert event.outcome == AuditOutcome.DENIED


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
        expected_sha256=SHA256,
        size_bytes=1,
        expires_at=timezone.now() + timedelta(minutes=15),
    )
    record.expected_sha256 = "b" * 64
    with pytest.raises(ValueError, match="immutable"):
        record.save()
    with pytest.raises(ValueError, match="immutable"):
        UploadRequest.objects.filter(pk=record.pk).update(size_bytes=2)


def test_fake_storage_enforces_orphan_to_promoted_copy_boundary():
    storage = FakeObjectStorage()
    source = f"uploads/orphan/issuance_input/{uuid.uuid4()}/{uuid.uuid4().hex}.bin"
    organization_id = source.split("/")[3]
    destination = f"inputs/issuance/{organization_id}/{uuid.uuid4()}.bin"
    signed = storage.presign_put(
        key=source, content_type="application/pdf", size_bytes=1, sha256=SHA256, expires=timedelta(minutes=15)
    )
    assert signed.headers["x-amz-meta-sha256"] == SHA256
    storage.put_object(key=source, content_type="application/pdf", size_bytes=1, sha256=SHA256)
    copied = storage.copy_verified(source=source, destination=destination, sha256=SHA256)
    assert copied.key == destination
    assert storage.head(key=destination).client_sha256_metadata == SHA256
    storage.delete(key=destination)
    assert storage.head(key=destination) is None
    with pytest.raises(ValueError, match="controlled"):
        storage.presign_get(key="uploads/orphan/../secret", expires=timedelta(minutes=1))


def test_fake_storage_rejects_invalid_copy_without_leaving_destination():
    storage = FakeObjectStorage()
    source = f"uploads/orphan/issuance_input/{uuid.uuid4()}/{uuid.uuid4().hex}.bin"
    organization_id = source.split("/")[3]
    destination = f"inputs/issuance/{organization_id}/{uuid.uuid4()}.bin"
    storage.put_object(key=source, content_type="application/pdf", size_bytes=1, sha256=SHA256)
    with pytest.raises(UploadRejected, match="STORAGE_COPY_MISMATCH"):
        storage.copy_verified(source=source, destination=destination, sha256="b" * 64)
    assert storage.head(key=destination) is None


@override_settings(
    OBJECT_STORAGE_ENDPOINT="",
    OBJECT_STORAGE_BUCKET="",
    OBJECT_STORAGE_ACCESS_KEY="",
    OBJECT_STORAGE_SECRET_KEY="",
)
def test_s3_configuration_fails_closed_when_any_required_environment_setting_is_absent():
    with pytest.raises(ImproperlyConfigured, match="R2 storage endpoint, bucket, and credentials"):
        S3ObjectStorage.from_settings()


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://r2.example.invalid",
        "https://user:pass@r2.example.invalid",
        "https://r2.example.invalid/path",
        "https://r2.example.invalid?token=x",
        "https://r2.example.invalid#fragment",
    ],
)
@override_settings(
    ENVIRONMENT="production",
    OBJECT_STORAGE_ENDPOINT_HINT="https://r2.example.invalid",
    OBJECT_STORAGE_BUCKET="bucket",
    OBJECT_STORAGE_ACCESS_KEY="fake-access-key",
    OBJECT_STORAGE_SECRET_KEY="fake-secret-key",
)
def test_production_storage_rejects_unsafe_or_nonmatching_endpoint(endpoint):
    with override_settings(OBJECT_STORAGE_ENDPOINT=endpoint):
        with pytest.raises(ImproperlyConfigured):
            S3ObjectStorage.from_settings()


@override_settings(
    ENVIRONMENT="production",
    OBJECT_STORAGE_ENDPOINT="https://other.example.invalid",
    OBJECT_STORAGE_ENDPOINT_HINT="https://r2.example.invalid",
    OBJECT_STORAGE_BUCKET="bucket",
    OBJECT_STORAGE_ACCESS_KEY="fake-access-key",
    OBJECT_STORAGE_SECRET_KEY="fake-secret-key",
)
def test_production_storage_endpoint_must_match_managed_hint():
    with pytest.raises(ImproperlyConfigured, match="managed endpoint hint"):
        S3ObjectStorage.from_settings()


@override_settings(
    ENVIRONMENT="local",
    OBJECT_STORAGE_ENDPOINT="http://minio:9000",
    OBJECT_STORAGE_ENDPOINT_HINT="",
    OBJECT_STORAGE_BUCKET="bucket",
    OBJECT_STORAGE_ACCESS_KEY="fake-access-key",
    OBJECT_STORAGE_SECRET_KEY="fake-secret-key",
)
def test_local_minio_http_requires_explicit_nonproduction_environment(monkeypatch):
    captured = {}

    def fake_client(*args, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=fake_client))
    S3ObjectStorage.from_settings()
    assert captured["endpoint_url"] == "http://minio:9000"


@override_settings(
    ENVIRONMENT="staging",
    OBJECT_STORAGE_ENDPOINT="https://r2.example.invalid",
    OBJECT_STORAGE_ENDPOINT_HINT="",
    OBJECT_STORAGE_BUCKET="bucket",
    OBJECT_STORAGE_ACCESS_KEY="fake-access-key",
    OBJECT_STORAGE_SECRET_KEY="fake-secret-key",
)
def test_storage_rejects_unknown_environment_instead_of_skipping_production_guards(monkeypatch):
    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(client=lambda *args, **kwargs: object()))
    with pytest.raises(ImproperlyConfigured, match="environment"):
        S3ObjectStorage.from_settings()


@pytest.mark.parametrize(
    ("source_kind", "destination_kind", "same_organization"),
    [
        ("issuance_input", "verification", True),
        ("verification_input", "issuance", True),
        ("issuance_input", "issuance", False),
    ],
)
def test_copy_rejects_cross_kind_or_cross_organization_boundaries(
    source_kind, destination_kind, same_organization
):
    storage = FakeObjectStorage()
    source_org = uuid.uuid4()
    destination_org = source_org if same_organization else uuid.uuid4()
    source = f"uploads/orphan/{source_kind}/{source_org}/{uuid.uuid4().hex}.bin"
    destination = f"inputs/{destination_kind}/{destination_org}/{uuid.uuid4()}.bin"
    storage.put_object(key=source, content_type="application/pdf", size_bytes=1, sha256=SHA256)

    with pytest.raises(ValueError, match="same organization and kind"):
        storage.copy_verified(source=source, destination=destination, sha256=SHA256)
    assert destination not in storage.objects


@pytest.mark.parametrize(
    "destination",
    [
        "inputs/issuance/not-a-uuid/not-a-uuid.bin",
        "inputs/issuance/00000000-0000-0000-0000-000000000000/../x.bin",
        "uploads/orphan/issuance_input/00000000-0000-0000-0000-000000000000/00000000000000000000000000000000.bin",
    ],
)
def test_copy_rejects_non_promoted_destination_grammar(destination):
    storage = FakeObjectStorage()
    organization_id = uuid.uuid4()
    source = f"uploads/orphan/issuance_input/{organization_id}/{uuid.uuid4().hex}.bin"
    storage.put_object(key=source, content_type="application/pdf", size_bytes=1, sha256=SHA256)
    with pytest.raises(ValueError, match="promoted-input"):
        storage.copy_verified(source=source, destination=destination, sha256=SHA256)


@pytest.mark.django_db
def test_new_upload_rows_require_expected_checksum_and_bounded_size(organization, actors):
    common = {
        "organization": organization,
        "requested_by": actors[Role.ISSUER],
        "purpose": UploadPurpose.ISSUANCE,
        "object_key": f"uploads/orphan/issuance_input/{organization.id}/{uuid.uuid4().hex}.bin",
        "expires_at": timezone.now() + timedelta(minutes=15),
    }
    with pytest.raises(ValidationError, match="expected checksum"):
        UploadRequest.objects.create(**common, expected_sha256=None, size_bytes=1)
    with pytest.raises(ValidationError, match="between one byte and ten MiB"):
        UploadRequest.objects.create(**common, expected_sha256=SHA256, size_bytes=MAX_UPLOAD_BYTES + 1)


@pytest.mark.django_db
def test_serializer_validation_denial_is_audited_without_request_details(browser_client, actors):
    login(browser_client, actors[Role.ISSUER])
    secret_filename = "private-client-name.pdf"
    response = browser_client.post(
        "/api/v1/uploads",
        data=json.dumps(upload_payload(filename=secret_filename, sha256="BAD")),
        content_type="application/json",
        **csrf_headers(browser_client),
    )
    assert response.status_code == 400
    event = AuditEvent.objects.latest("created_at")
    assert event.action == "upload.intent.denied"
    assert event.metadata == {"safe_error_code": "UPLOAD_SHA256"}
    assert secret_filename not in str(event.metadata)
    assert "BAD" not in str(event.metadata)


@pytest.mark.django_db
def test_complete_serializer_validation_denial_is_audited_without_payload(browser_client, actors, storage):
    login(browser_client, actors[Role.ISSUER])
    created = browser_client.post(
        "/api/v1/uploads", data=json.dumps(upload_payload()), content_type="application/json", **csrf_headers(browser_client)
    ).json()
    response = browser_client.post(
        f"/api/v1/uploads/{created['id']}/complete",
        data=json.dumps({"sha256": "provider-detail-or-client-payload"}),
        content_type="application/json",
        **csrf_headers(browser_client),
    )
    assert response.status_code == 400
    event = AuditEvent.objects.latest("created_at")
    assert event.action == "upload.complete.denied"
    assert event.metadata == {"safe_error_code": "UPLOAD_SHA256"}


@pytest.mark.django_db
def test_completion_locks_and_rechecks_before_finalizing(actors, storage, monkeypatch):
    actor = actors[Role.ISSUER]
    with override_settings(SPLITBIND_OBJECT_STORAGE=storage):
        intent = create_upload(
            actor, kind="issuance_input", filename="x.pdf", content_type="application/pdf", size_bytes=1, sha256=SHA256
        )
        storage.put_object(key=intent.record.object_key, content_type="application/pdf", size_bytes=1, sha256=SHA256)
        called = False
        original = UploadRequest.objects.select_for_update

        def observed_lock(*args, **kwargs):
            nonlocal called
            called = True
            return original(*args, **kwargs)

        monkeypatch.setattr(UploadRequest.objects, "select_for_update", observed_lock)
        complete_upload(actor, upload_id=intent.record.id, sha256=SHA256)
        complete_upload(actor, upload_id=intent.record.id, sha256=SHA256)

    assert called
    assert AuditEvent.objects.filter(action="upload.completed").count() == 1


@pytest.mark.django_db
def test_completion_rechecks_expiry_after_storage_head(actors, storage, monkeypatch):
    actor = actors[Role.ISSUER]
    with override_settings(SPLITBIND_OBJECT_STORAGE=storage):
        intent = create_upload(
            actor,
            kind="issuance_input",
            filename="x.pdf",
            content_type="application/pdf",
            size_bytes=1,
            sha256=SHA256,
        )
        storage.put_object(
            key=intent.record.object_key,
            content_type="application/pdf",
            size_bytes=1,
            sha256=SHA256,
        )
        observed_times = iter(
            [
                intent.record.expires_at - timedelta(seconds=1),
                intent.record.expires_at,
                intent.record.expires_at,
                intent.record.expires_at,
            ]
        )
        monkeypatch.setattr(
            "splitbind.uploads.services.timezone.now", lambda: next(observed_times)
        )

        with pytest.raises(UploadRejected, match="UPLOAD_EXPIRED"):
            complete_upload(actor, upload_id=intent.record.id, sha256=SHA256)

    intent.record.refresh_from_db()
    assert intent.record.finalized_at is None
    assert AuditEvent.objects.filter(action="upload.completed").count() == 0


class CompletionConcurrencyContractTests(TransactionTestCase):
    def test_concurrent_completion_writes_one_success_event(self):
        if connection.vendor != "postgresql":
            self.skipTest("SQLite does not implement row-level SELECT FOR UPDATE; PostgreSQL runtime remains the P3 gate")
        organization = Organization.objects.create(name="Concurrent Upload Organization", slug="concurrent-upload")
        actor = create_user(organization, Role.ISSUER, "concurrent")
        storage = FakeObjectStorage()
        with override_settings(SPLITBIND_OBJECT_STORAGE=storage):
            intent = create_upload(
                actor,
                kind="issuance_input",
                filename="x.pdf",
                content_type="application/pdf",
                size_bytes=1,
                sha256=SHA256,
            )
            storage.put_object(
                key=intent.record.object_key,
                content_type="application/pdf",
                size_bytes=1,
                sha256=SHA256,
            )
            barrier = threading.Barrier(2)
            errors = []

            def finalize():
                close_old_connections()
                try:
                    barrier.wait(timeout=5)
                    complete_upload(actor, upload_id=intent.record.id, sha256=SHA256)
                except Exception as error:
                    errors.append(error)
                finally:
                    close_old_connections()

            threads = [threading.Thread(target=finalize) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)

        assert all(not thread.is_alive() for thread in threads)
        assert errors == []
        assert AuditEvent.objects.filter(action="upload.completed").count() == 1


class UploadLegacyMigrationContractTests(TransactionTestCase):
    def test_nullable_pre_b3_row_survives_expectation_hardening_migration(self):
        executor = MigrationExecutor(connection)
        old_target = [("uploads", "0002_alter_uploadrequest_size_bytes")]
        latest_targets = executor.loader.graph.leaf_nodes()
        try:
            executor.migrate(old_target)
            old_apps = executor.loader.project_state(old_target).apps
            organization_model = old_apps.get_model("access", "Organization")
            user_model = old_apps.get_model("access", "User")
            upload_model = old_apps.get_model("uploads", "UploadRequest")
            organization = organization_model.objects.create(name="Legacy", slug="legacy-upload")
            actor = user_model.objects.create(
                username="legacy-upload-user",
                password="unusable-test-value",
                organization_id=organization.id,
                role=Role.ISSUER,
                is_active=True,
                is_staff=False,
                is_superuser=False,
                date_joined=timezone.now(),
            )
            legacy = upload_model.objects.create(
                organization_id=organization.id,
                requested_by_id=actor.id,
                purpose=UploadPurpose.ISSUANCE,
                object_key="legacy/pre-b3-nullable-row.bin",
                sha256=None,
                size_bytes=None,
                expires_at=timezone.now(),
            )
            # Rebuild the executor after migrating backwards so its applied
            # migration snapshot reflects the database before moving forward.
            MigrationExecutor(connection).migrate(latest_targets)
            migrated = UploadRequest._base_manager.get(pk=legacy.pk)
            assert migrated.expected_sha256 is None
            assert migrated.size_bytes is None
        finally:
            MigrationExecutor(connection).migrate(latest_targets)
