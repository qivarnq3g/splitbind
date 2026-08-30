import importlib
import uuid
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from splitbind.access.models import Organization, Recipient, Role, User
from splitbind.documents.models import Document, Issuance
from splitbind.uploads.models import UploadPurpose, UploadRequest


@pytest.mark.django_db
def test_cleanup_timestamp_reverse_guards_fail_closed_before_evidence_loss():
    org = Organization.objects.create(name="Migration Guard", slug=f"guard-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(username="guard-user", password="test", organization=org, role=Role.ISSUER)
    upload = UploadRequest.objects.create(
        organization=org,
        requested_by=actor,
        purpose=UploadPurpose.ISSUANCE,
        object_key=f"uploads/orphan/issuance_input/{org.id}/{uuid.uuid4().hex}.bin",
        expected_sha256="a" * 64,
        size_bytes=1,
        expires_at=timezone.now(),
    )
    document = Document.objects.create(
        organization=org,
        created_by=actor,
        upload_request=upload,
        source_object_key=f"inputs/issuance/{org.id}/{upload.id}.bin",
        expected_source_sha256="a" * 64,
        page_count=1,
    )
    recipient = Recipient.objects.create(
        organization=org, external_reference="R", display_name="Synthetic",
    )
    issuance = Issuance.objects.create(
        organization=org,
        created_by=actor,
        document=document,
        recipient=recipient,
        output_object_key=f"outputs/issuance/{org.id}/{uuid.uuid4()}.pdf",
        output_sha256="b" * 64,
    )
    deletion_time = timezone.now()
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE uploads_uploadrequest SET orphan_deleted_at = %s WHERE id = %s",
            [deletion_time, upload.id.hex],
        )
        cursor.execute(
            "UPDATE documents_issuance SET output_deleted_at = %s WHERE id = %s",
            [deletion_time, issuance.id.hex],
        )
    editor = SimpleNamespace(connection=connection)
    upload_migration = importlib.import_module(
        "splitbind.uploads.migrations.0005_cleanup_timestamps"
    )
    document_migration = importlib.import_module(
        "splitbind.documents.migrations.0004_issuance_output_deletion"
    )

    with pytest.raises(RuntimeError, match="cleanup evidence"):
        upload_migration.refuse_cleanup_evidence_rollback(apps, editor)
    with pytest.raises(RuntimeError, match="output deletion evidence"):
        document_migration.refuse_output_evidence_rollback(apps, editor)

    upload.refresh_from_db()
    issuance.refresh_from_db()
    assert upload.orphan_deleted_at is not None
    assert issuance.output_deleted_at is not None


@pytest.mark.django_db(transaction=True)
def test_signing_key_constraint_preflight_rejects_invalid_legacy_rows_with_actionable_error():
    target = [("access", "0003_alter_user_managers")]
    executor = MigrationExecutor(connection)
    executor.migrate(target)
    old_apps = executor.loader.project_state(target).apps
    LegacyOrganization = old_apps.get_model("access", "Organization")
    LegacySigningKey = old_apps.get_model("access", "SigningKey")
    org = LegacyOrganization.objects.create(name="Legacy key", slug=f"legacy-key-{uuid.uuid4().hex[:8]}")
    key = LegacySigningKey.objects.create(
        organization=org, key_id="legacy-key", public_key="legacy-public-evidence",
        valid_from=timezone.now(), status="legacy-invalid",
    )
    migration = importlib.import_module("splitbind.access.migrations.0004_signing_key_lifecycle")

    try:
        with pytest.raises(RuntimeError, match="invalid legacy signing-key lifecycle"):
            migration.validate_legacy_signing_keys(old_apps, SimpleNamespace(connection=connection))
    finally:
        LegacySigningKey.objects.filter(pk=key.pk).delete()
        MigrationExecutor(connection).migrate([("access", "0005_alter_signingkey_options")])


@pytest.mark.django_db
def test_signing_key_constraint_reverse_refuses_to_drop_registry_guards_with_evidence():
    org = Organization.objects.create(name="Registry guard", slug=f"registry-guard-{uuid.uuid4().hex[:8]}")
    from splitbind.access.services import register_signing_key
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    pem = Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    register_signing_key(
        organization=org, key_id="registry-guard", public_key=pem,
        valid_from=timezone.now(),
    )
    migration = importlib.import_module("splitbind.access.migrations.0004_signing_key_lifecycle")

    with pytest.raises(RuntimeError, match="registry evidence exists"):
        migration.refuse_lifecycle_guard_rollback(apps, SimpleNamespace(connection=connection))


@pytest.mark.django_db(transaction=True)
def test_promotion_transition_clock_migration_backfills_legacy_created_at():
    old_target = [("uploads", "0006_alter_uploadrequest_options")]
    latest_targets = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        MigrationExecutor(connection).migrate(old_target)
        old_apps = MigrationExecutor(connection).loader.project_state(old_target).apps
        LegacyOrganization = old_apps.get_model("access", "Organization")
        LegacyUser = old_apps.get_model("access", "User")
        LegacyUpload = old_apps.get_model("uploads", "UploadRequest")
        org = LegacyOrganization.objects.create(
            name="Legacy transition", slug=f"legacy-transition-{uuid.uuid4().hex[:8]}",
        )
        actor = LegacyUser.objects.create(
            username="legacy-transition", password="unusable-test-value",
            organization_id=org.id, role=Role.ISSUER, is_active=True,
            is_staff=False, is_superuser=False, date_joined=timezone.now(),
        )
        upload_id = uuid.uuid4()
        legacy = LegacyUpload.objects.create(
            id=upload_id,
            organization_id=org.id,
            requested_by_id=actor.id,
            purpose=UploadPurpose.ISSUANCE,
            object_key=f"uploads/orphan/issuance_input/{org.id}/{upload_id.hex}.bin",
            expected_sha256="a" * 64,
            size_bytes=1,
            expires_at=timezone.now(),
        )
        legacy_created_at = legacy.created_at

        MigrationExecutor(connection).migrate(latest_targets)
        migrated = UploadRequest.objects.get(pk=legacy.pk)
        assert migrated.promotion_status_changed_at == legacy_created_at
    finally:
        MigrationExecutor(connection).migrate(latest_targets)
