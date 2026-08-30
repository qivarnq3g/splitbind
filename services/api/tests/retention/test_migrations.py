import importlib
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from splitbind.access.models import Organization, Recipient, Role, User
from splitbind.documents.models import Document, Issuance
from splitbind.integrations.storage.fake import FakeObjectStorage
from splitbind.retention.services import STALE_COPYING_AGE, cleanup_expired
from splitbind.retention.capabilities import _allow_cleanup_schedule_write
from splitbind.uploads.models import (
    CleanupScheduleState, PromotionStatus, UploadPurpose, UploadRequest,
)


def cleanup_schedule():
    with _allow_cleanup_schedule_write():
        schedule, _created = CleanupScheduleState.objects.get_or_create(pk=1)
    return schedule


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


@pytest.mark.django_db
def test_reconciliation_observation_reverse_guard_preserves_retry_evidence():
    org = Organization.objects.create(name="Reconcile guard", slug=f"reconcile-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(
        username="reconcile-guard", password="test", organization=org, role=Role.ISSUER,
    )
    upload = UploadRequest.objects.create(
        organization=org,
        requested_by=actor,
        purpose=UploadPurpose.ISSUANCE,
        object_key=f"uploads/orphan/issuance_input/{org.id}/{uuid.uuid4().hex}.bin",
        expected_sha256="a" * 64,
        size_bytes=1,
        expires_at=timezone.now(),
    )
    observed_at = timezone.now()
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE uploads_uploadrequest SET promotion_target_reconciled_at = %s WHERE id = %s",
            [observed_at, upload.id.hex],
        )
    migration = importlib.import_module(
        "splitbind.uploads.migrations.0008_uploadrequest_promotion_target_reconciled_at"
    )

    with pytest.raises(RuntimeError, match="reconciliation evidence"):
        migration.refuse_reconciliation_evidence_rollback(
            apps, SimpleNamespace(connection=connection),
        )


@pytest.mark.django_db
def test_cleanup_schedule_reverse_guard_preserves_used_fairness_position():
    schedule = cleanup_schedule()
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE uploads_cleanupschedulestate SET has_run = %s WHERE id = %s",
            [True, schedule.pk],
        )
    migration = importlib.import_module(
        "splitbind.uploads.migrations.0009_cleanup_schedule_fairness"
    )

    with pytest.raises(RuntimeError, match="fairness position"):
        migration.refuse_used_schedule_rollback(
            apps, SimpleNamespace(connection=connection),
        )


@pytest.mark.django_db(transaction=True)
def test_reconciliation_claim_migration_empty_round_trip_preserves_scheduler_position():
    cursor_at = timezone.now()
    cursor_id = uuid.uuid4()
    schedule = cleanup_schedule()
    schedule.next_lane = "reconciliation"
    schedule.reconciliation_cursor_at = cursor_at
    schedule.reconciliation_cursor_id = cursor_id
    schedule.has_run = True
    with _allow_cleanup_schedule_write():
        schedule.save(
            update_fields=[
                "next_lane",
                "reconciliation_cursor_at",
                "reconciliation_cursor_id",
                "has_run",
            ]
        )

    old_target = [("uploads", "0009_cleanup_schedule_fairness")]
    latest_targets = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        MigrationExecutor(connection).migrate(old_target)
        old_apps = MigrationExecutor(connection).loader.project_state(old_target).apps
        OldSchedule = old_apps.get_model("uploads", "CleanupScheduleState")
        preserved = OldSchedule.objects.get(pk=1)
        assert preserved.next_lane == "reconciliation"
        assert preserved.reconciliation_cursor_at == cursor_at
        assert preserved.reconciliation_cursor_id == cursor_id
        assert preserved.has_run is True

        MigrationExecutor(connection).migrate(latest_targets)
        migrated = CleanupScheduleState.objects.get(pk=1)
        assert migrated.reconciliation_claim_upload_id is None
        assert migrated.reconciliation_claim_token is None
        assert migrated.reconciliation_claim_expires_at is None
    finally:
        MigrationExecutor(connection).migrate(latest_targets)


@pytest.mark.django_db(transaction=True)
def test_reconciliation_claim_migration_refuses_live_claim_reverse_and_preserves_evidence():
    schedule = cleanup_schedule()
    upload_id = uuid.uuid4()
    token = uuid.uuid4()
    expires_at = timezone.now() + timedelta(minutes=5)
    schedule.reconciliation_claim_upload_id = upload_id
    schedule.reconciliation_claim_token = token
    schedule.reconciliation_claim_expires_at = expires_at
    with _allow_cleanup_schedule_write():
        schedule.save(
            update_fields=[
                "reconciliation_claim_upload_id",
                "reconciliation_claim_token",
                "reconciliation_claim_expires_at",
            ]
        )

    with pytest.raises(RuntimeError, match="reconciliation claim is live"):
        MigrationExecutor(connection).migrate(
            [("uploads", "0009_cleanup_schedule_fairness")]
        )

    schedule.refresh_from_db()
    assert schedule.reconciliation_claim_upload_id == upload_id
    assert schedule.reconciliation_claim_token == token
    assert schedule.reconciliation_claim_expires_at == expires_at


@pytest.mark.django_db
def test_reconciliation_claim_database_constraint_rejects_partial_state():
    schedule = cleanup_schedule()

    with pytest.raises(IntegrityError), transaction.atomic():
        CleanupScheduleState.objects.filter(pk=schedule.pk)._update(
            [
                (
                    CleanupScheduleState._meta.get_field(
                        "reconciliation_claim_upload_id"
                    ),
                    None,
                    uuid.uuid4(),
                )
            ]
        )

    schedule.refresh_from_db()
    assert schedule.reconciliation_claim_upload_id is None
    assert schedule.reconciliation_claim_token is None
    assert schedule.reconciliation_claim_expires_at is None


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


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("status", [PromotionStatus.COPYING, PromotionStatus.FAILED])
def test_promotion_clock_migration_gives_active_legacy_work_a_fresh_stale_window(status):
    old_target = [("uploads", "0006_alter_uploadrequest_options")]
    latest_targets = MigrationExecutor(connection).loader.graph.leaf_nodes()
    try:
        MigrationExecutor(connection).migrate(old_target)
        old_apps = MigrationExecutor(connection).loader.project_state(old_target).apps
        LegacyOrganization = old_apps.get_model("access", "Organization")
        LegacyUser = old_apps.get_model("access", "User")
        LegacyUpload = old_apps.get_model("uploads", "UploadRequest")
        org = LegacyOrganization.objects.create(
            name="Active legacy promotion",
            slug=f"active-legacy-{status}-{uuid.uuid4().hex[:6]}",
        )
        actor = LegacyUser.objects.create(
            username=f"active-legacy-{status}-{uuid.uuid4().hex[:6]}",
            password="unusable-test-value", organization_id=org.id,
            role=Role.ISSUER, is_active=True, is_staff=False,
            is_superuser=False, date_joined=timezone.now(),
        )
        upload_id = uuid.uuid4()
        old_time = timezone.now() - timedelta(days=30)
        target_key = f"inputs/issuance/{org.id}/{upload_id}.bin"
        legacy = LegacyUpload.objects.create(
            id=upload_id, organization_id=org.id, requested_by_id=actor.id,
            purpose=UploadPurpose.ISSUANCE,
            object_key=f"uploads/orphan/issuance_input/{org.id}/{upload_id.hex}.bin",
            expected_sha256="a" * 64, size_bytes=1, expires_at=old_time,
            finalized_at=old_time, orphan_deleted_at=old_time,
            promotion_target_key=target_key, promotion_status=status,
            safe_error_code="PROMOTION_COPY_FAILED" if status == PromotionStatus.FAILED else None,
        )
        LegacyUpload.objects.filter(pk=legacy.pk).update(created_at=old_time)

        migration_started_at = timezone.now()
        MigrationExecutor(connection).migrate(latest_targets)
        migration_finished_at = timezone.now()
        migrated = UploadRequest.objects.get(pk=legacy.pk)
        assert migration_started_at <= migrated.promotion_status_changed_at <= migration_finished_at

        storage = FakeObjectStorage()
        storage.inject_object(
            key=target_key, content_type="application/pdf", size_bytes=1,
            sha256="a" * 64,
        )
        assert cleanup_expired(
            now=migrated.promotion_status_changed_at + STALE_COPYING_AGE - timedelta(seconds=1),
            storage=storage, batch_size=1,
        ) == 0
        assert target_key in storage.objects
        assert cleanup_expired(
            now=migrated.promotion_status_changed_at + STALE_COPYING_AGE + timedelta(seconds=1),
            storage=storage, batch_size=1,
        ) == 1
    finally:
        MigrationExecutor(connection).migrate(latest_targets)
