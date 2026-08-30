import threading
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.utils import timezone

from splitbind.access.models import Organization, Role, User
from splitbind.access.models import Recipient
from splitbind.audit.models import AuditEvent, AuditOutcome
from splitbind.integrations.storage.fake import FakeObjectStorage
from splitbind.jobs.models import Job, JobKind, JobStatus
from splitbind.jobs.services import create_issuance, create_verification
from splitbind.documents.models import Document, Issuance
from splitbind.retention.services import STALE_COPYING_AGE, cleanup_expired
from splitbind.retention import services as retention_services
from splitbind.uploads.models import (
    CleanupScheduleState, PromotionStatus, UploadPurpose, UploadRequest,
)
from django.core.exceptions import ValidationError


SHA256 = "a" * 64


def upload(
    org, actor, *, created_at, status=PromotionStatus.NONE,
    purpose=UploadPurpose.ISSUANCE, upload_id=None,
):
    kind = "issuance_input" if purpose == UploadPurpose.ISSUANCE else "verification_input"
    upload_id = upload_id or uuid.uuid4()
    record = UploadRequest.objects.create(
        id=upload_id,
        organization=org,
        requested_by=actor,
        purpose=purpose,
        object_key=f"uploads/orphan/{kind}/{org.id}/{upload_id.hex}.bin",
        expected_sha256=SHA256,
        size_bytes=1,
        expires_at=created_at + timedelta(minutes=15),
        finalized_at=created_at,
    )
    UploadRequest._base_manager.filter(pk=record.pk).update(created_at=created_at)
    record.refresh_from_db()
    if status != PromotionStatus.NONE:
        target = f"inputs/issuance/{org.id}/{record.id}.bin"
        with pytest.MonkeyPatch.context() as patcher:
            patcher.setattr(
                "splitbind.uploads.models.timezone",
                SimpleNamespace(now=lambda: created_at, is_naive=timezone.is_naive),
            )
            record.save_promotion(
                status=PromotionStatus.COPYING, target_key=target,
                safe_error_code=None,
            )
            if status == PromotionStatus.FAILED:
                record.save_promotion(
                    status=PromotionStatus.FAILED, target_key=target,
                    safe_error_code="PROMOTION_COPY_FAILED",
                )
    return record


@pytest.mark.django_db
def test_cleanup_deletes_only_exact_expired_orphan_once_and_records_system_audit():
    now = timezone.now()
    org = Organization.objects.create(name="Cleanup", slug=f"cleanup-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(username="issuer", password="test", organization=org, role=Role.ISSUER)
    expired = upload(org, actor, created_at=now - timedelta(hours=25))
    fresh = upload(org, actor, created_at=now - timedelta(hours=23))
    storage = FakeObjectStorage()
    for record in (expired, fresh):
        storage.inject_object(key=record.object_key, content_type="application/pdf", size_bytes=1, sha256=SHA256)

    first = cleanup_expired(now=now, storage=storage, batch_size=10)
    second = cleanup_expired(now=now, storage=storage, batch_size=10)

    expired.refresh_from_db()
    assert first == 1 and second == 0
    assert expired.orphan_deleted_at is not None
    assert fresh.object_key in storage.objects
    assert AuditEvent.objects.filter(
        actor__isnull=True, target_id=str(expired.id), outcome=AuditOutcome.SUCCEEDED,
    ).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("status", [PromotionStatus.FAILED, PromotionStatus.COPYING])
def test_stale_promotion_deletes_recorded_target_but_preserves_ownership(status):
    now = timezone.now()
    org = Organization.objects.create(name="Promotion", slug=f"promotion-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(username=f"issuer-{status}", password="test", organization=org, role=Role.ISSUER)
    record = upload(org, actor, created_at=now - STALE_COPYING_AGE - timedelta(minutes=1), status=status)
    storage = FakeObjectStorage()
    storage.inject_object(key=record.promotion_target_key, content_type="application/pdf", size_bytes=1, sha256=SHA256)

    cleanup_expired(now=now, storage=storage, batch_size=10)

    record.refresh_from_db()
    assert record.promotion_target_deleted_at is not None
    assert record.promotion_target_key is not None
    assert record.promotion_status == status
    assert record.promotion_target_key not in storage.objects


@pytest.mark.django_db
def test_stale_promotion_age_starts_at_each_state_transition():
    now = timezone.now()
    org = Organization.objects.create(name="Transition age", slug=f"transition-age-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(username="transition-age", password="test", organization=org, role=Role.ISSUER)
    record = upload(org, actor, created_at=now - timedelta(days=2))
    target = f"inputs/issuance/{org.id}/{record.id}.bin"
    storage = FakeObjectStorage()
    storage.inject_object(key=target, content_type="application/pdf", size_bytes=1, sha256=SHA256)

    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(
            "splitbind.uploads.models.timezone",
            SimpleNamespace(now=lambda: now, is_naive=timezone.is_naive),
        )
        record.save_promotion(
            status=PromotionStatus.COPYING, target_key=target, safe_error_code=None,
        )
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE uploads_uploadrequest SET orphan_deleted_at = %s WHERE id = %s",
            [now, record.id.hex],
        )
    copying_at = record.promotion_status_changed_at

    assert copying_at == now
    assert cleanup_expired(now=now, storage=storage, batch_size=1) == 0
    assert cleanup_expired(
        now=now + STALE_COPYING_AGE - timedelta(seconds=1), storage=storage, batch_size=1,
    ) == 0
    assert cleanup_expired(
        now=now + STALE_COPYING_AGE + timedelta(seconds=1), storage=storage, batch_size=1,
    ) == 1


@pytest.mark.django_db
def test_every_promotion_state_transition_refreshes_durable_age():
    start = timezone.now()
    org = Organization.objects.create(name="Transition clock", slug=f"transition-clock-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(username="transition-clock", password="test", organization=org, role=Role.ISSUER)
    record = upload(org, actor, created_at=start - timedelta(days=2))
    target = f"inputs/issuance/{org.id}/{record.id}.bin"

    moments = iter(start + timedelta(minutes=index) for index in range(4))
    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(
            "splitbind.uploads.models.timezone",
            SimpleNamespace(now=lambda: next(moments), is_naive=timezone.is_naive),
        )
        record.save_promotion(
            status=PromotionStatus.COPYING, target_key=target, safe_error_code=None,
        )
        copying_at = record.promotion_status_changed_at
        record.save_promotion(
            status=PromotionStatus.FAILED, target_key=target,
            safe_error_code="PROMOTION_COPY_FAILED",
        )
        failed_at = record.promotion_status_changed_at
        record.save_promotion(
            status=PromotionStatus.COPYING, target_key=target, safe_error_code=None,
        )
        retry_at = record.promotion_status_changed_at
        record.save_promotion(
            status=PromotionStatus.ATTACHED, target_key=target, safe_error_code=None,
        )
        attached_at = record.promotion_status_changed_at

    assert copying_at < failed_at < retry_at < attached_at


@pytest.mark.django_db
def test_promotion_transition_clock_is_immutable_outside_transition_service():
    now = timezone.now()
    org = Organization.objects.create(name="Clock immutable", slug=f"clock-immutable-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(username="clock-immutable", password="test", organization=org, role=Role.ISSUER)
    record = upload(org, actor, created_at=now)
    forged = now - timedelta(days=30)

    record.promotion_status_changed_at = forged
    with pytest.raises(ValueError, match="immutable"):
        record.save(update_fields=["promotion_status_changed_at"])
    with pytest.raises(ValueError, match="immutable"):
        UploadRequest._base_manager.filter(pk=record.pk).update(
            promotion_status_changed_at=forged,
        )
    record.refresh_from_db()
    record.promotion_status_changed_at = forged
    with pytest.raises(ValueError, match="immutable"):
        UploadRequest.objects.bulk_update([record], ["promotion_status_changed_at"])


@pytest.mark.django_db
def test_promotion_transition_timestamp_is_captured_after_the_row_lock(monkeypatch):
    now = timezone.now()
    org = Organization.objects.create(name="Lock clock", slug=f"lock-clock-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(
        username="lock-clock", password="test", organization=org, role=Role.ISSUER,
    )
    record = upload(org, actor, created_at=now)
    target = f"inputs/issuance/{org.id}/{record.id}.bin"
    clock_was_read = False

    def observed_now():
        nonlocal clock_was_read
        clock_was_read = True
        return now + timedelta(minutes=1)

    from django.db.models.query import QuerySet
    original_get = QuerySet.get

    def checked_get(queryset, *args, **kwargs):
        if queryset.model is UploadRequest and queryset.query.select_for_update:
            assert clock_was_read is False
        return original_get(queryset, *args, **kwargs)

    monkeypatch.setattr(QuerySet, "get", checked_get)
    monkeypatch.setattr(
        "splitbind.uploads.models.timezone",
        SimpleNamespace(now=observed_now, is_naive=timezone.is_naive),
    )

    record.save_promotion(
        status=PromotionStatus.COPYING, target_key=target, safe_error_code=None,
    )
    assert record.promotion_status_changed_at == now + timedelta(minutes=1)


@pytest.mark.django_db
def test_cleaned_promotion_target_is_a_permanent_transition_fence():
    now = timezone.now()
    org = Organization.objects.create(name="Cleanup fence", slug=f"cleanup-fence-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(
        username="cleanup-fence", password="test", organization=org, role=Role.ISSUER,
    )
    record = upload(
        org, actor, created_at=now - STALE_COPYING_AGE - timedelta(minutes=1),
        status=PromotionStatus.FAILED,
    )
    storage = FakeObjectStorage()
    storage.inject_object(
        key=record.promotion_target_key, content_type="application/pdf", size_bytes=1,
        sha256=SHA256,
    )
    assert cleanup_expired(now=now, storage=storage, batch_size=1) == 1
    record.refresh_from_db()

    with pytest.raises(ValueError, match="deleted"):
        record.save_promotion(
            status=PromotionStatus.COPYING,
            target_key=record.promotion_target_key,
            safe_error_code=None,
        )
    record.refresh_from_db()
    assert record.promotion_status == PromotionStatus.FAILED
    assert record.promotion_target_deleted_at is not None


@pytest.mark.django_db
def test_next_cleanup_scan_removes_a_late_copy_after_promotion_tombstone():
    now = timezone.now()
    org = Organization.objects.create(name="Late copy", slug=f"late-copy-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(
        username="late-copy", password="test", organization=org, role=Role.ISSUER,
    )
    record = upload(
        org, actor, created_at=now - STALE_COPYING_AGE - timedelta(minutes=1),
        status=PromotionStatus.FAILED,
    )
    storage = FakeObjectStorage()

    assert cleanup_expired(now=now, storage=storage, batch_size=1) == 1
    record.refresh_from_db()
    assert record.promotion_target_deleted_at is not None
    assert record.promotion_target_reconciled_at is None

    storage.inject_object(
        key=record.promotion_target_key, content_type="application/pdf", size_bytes=1,
        sha256=SHA256,
    )
    unrelated = f"inputs/issuance/{org.id}/{uuid.uuid4()}.bin"
    storage.inject_object(
        key=unrelated, content_type="application/pdf", size_bytes=1, sha256=SHA256,
    )

    assert cleanup_expired(now=now, storage=storage, batch_size=1) == 0
    record.refresh_from_db()
    assert record.promotion_target_key not in storage.objects
    assert unrelated in storage.objects
    assert record.promotion_target_reconciled_at >= now


@pytest.mark.django_db
def test_failed_late_copy_reconciliation_remains_durably_retryable():
    now = timezone.now()
    org = Organization.objects.create(name="Late retry", slug=f"late-retry-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(
        username="late-retry", password="test", organization=org, role=Role.ISSUER,
    )
    record = upload(
        org, actor, created_at=now - STALE_COPYING_AGE - timedelta(minutes=1),
        status=PromotionStatus.FAILED,
    )
    storage = FakeObjectStorage()
    assert cleanup_expired(now=now, storage=storage, batch_size=1) == 1
    storage.inject_object(
        key=record.promotion_target_key, content_type="application/pdf", size_bytes=1,
        sha256=SHA256,
    )
    storage.fail_next("delete", "https://provider.invalid/private?token=secret")

    failed_at = now + timedelta(minutes=1)
    assert cleanup_expired(now=failed_at, storage=storage, batch_size=1) == 0
    record.refresh_from_db()
    assert record.promotion_target_key in storage.objects
    assert record.promotion_target_reconciled_at == failed_at
    failure = AuditEvent.objects.get(action="object.promotion.reconciliation.failed")
    assert failure.metadata == {"safe_error_code": "STORAGE_DELETE_RETRY"}

    second_failed_at = failed_at + timedelta(seconds=1)
    storage.fail_next("delete", "another provider detail that must remain private")
    assert cleanup_expired(now=second_failed_at, storage=storage, batch_size=1) == 0
    record.refresh_from_db()
    assert record.promotion_target_reconciled_at == second_failed_at
    assert AuditEvent.objects.filter(
        action="object.promotion.reconciliation.failed",
    ).count() == 1

    retry_at = second_failed_at + timedelta(seconds=1)
    assert cleanup_expired(now=retry_at, storage=storage, batch_size=1) == 0
    record.refresh_from_db()
    assert record.promotion_target_key not in storage.objects
    assert record.promotion_target_reconciled_at == retry_at


@pytest.mark.django_db
def test_repeated_reconciliation_is_exact_key_idempotent_with_bounded_audit():
    now = timezone.now()
    org = Organization.objects.create(name="Late idempotent", slug=f"late-idem-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(
        username="late-idem", password="test", organization=org, role=Role.ISSUER,
    )
    record = upload(
        org, actor, created_at=now - STALE_COPYING_AGE - timedelta(minutes=1),
        status=PromotionStatus.FAILED,
    )
    storage = FakeObjectStorage()
    assert cleanup_expired(now=now, storage=storage, batch_size=1) == 1
    tombstone = AuditEvent.objects.get(action="object.promotion.deleted")

    first = now + timedelta(minutes=1)
    assert cleanup_expired(now=first, storage=storage, batch_size=1) == 0
    storage.inject_object(
        key=record.promotion_target_key, content_type="application/pdf", size_bytes=1,
        sha256=SHA256,
    )
    unrelated = f"inputs/issuance/{org.id}/{uuid.uuid4()}.bin"
    storage.inject_object(
        key=unrelated, content_type="application/pdf", size_bytes=1, sha256=SHA256,
    )
    second = first + timedelta(seconds=1)
    assert cleanup_expired(now=second, storage=storage, batch_size=1) == 0

    assert record.promotion_target_key not in storage.objects
    assert unrelated in storage.objects
    assert AuditEvent.objects.filter(pk=tombstone.pk).count() == 1
    assert AuditEvent.objects.filter(action="object.promotion.deleted").count() == 1
    assert AuditEvent.objects.filter(
        action="object.promotion.reconciliation.succeeded",
    ).count() == 1


@pytest.mark.django_db
def test_reconciliation_observation_is_service_only_and_monotonic():
    now = timezone.now()
    org = Organization.objects.create(name="Reconcile evidence", slug=f"recon-evidence-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(
        username="recon-evidence", password="test", organization=org, role=Role.ISSUER,
    )
    record = upload(
        org, actor, created_at=now - STALE_COPYING_AGE - timedelta(minutes=1),
        status=PromotionStatus.FAILED,
    )
    storage = FakeObjectStorage()
    assert cleanup_expired(now=now, storage=storage, batch_size=1) == 1
    observed_at = now + timedelta(seconds=1)
    assert cleanup_expired(now=observed_at, storage=storage, batch_size=1) == 0
    record.refresh_from_db()

    with pytest.raises(ValidationError, match="retention service"):
        UploadRequest._base_manager.filter(pk=record.pk).update(
            promotion_target_reconciled_at=None,
        )
    record.promotion_target_reconciled_at = observed_at - timedelta(seconds=1)
    with pytest.raises(ValidationError, match="retention service"):
        record.save(update_fields=["promotion_target_reconciled_at"])
    record.refresh_from_db()
    assert record.promotion_target_reconciled_at == observed_at


def _set_promotion_tombstone(record, *, at, target_key=None):
    target_key = target_key or record.promotion_target_key
    stored_at = connection.ops.adapt_datetimefield_value(at)
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE uploads_uploadrequest SET promotion_target_key = %s, "
            "promotion_target_deleted_at = %s WHERE id = %s",
            [target_key, stored_at, record.id.hex],
        )
    record.refresh_from_db()
    return record


@pytest.mark.django_db
def test_batch_one_persistently_alternates_ordinary_and_reconciliation_after_restart():
    now = timezone.now()
    org = Organization.objects.create(name="Fair lanes", slug=f"fair-lanes-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(
        username="fair-lanes", password="test", organization=org, role=Role.ISSUER,
    )
    ordinary = upload(org, actor, created_at=now - timedelta(hours=25))
    reconciled = upload(
        org, actor, created_at=now - STALE_COPYING_AGE - timedelta(minutes=1),
        status=PromotionStatus.FAILED,
    )
    _set_promotion_tombstone(reconciled, at=now - timedelta(minutes=1))
    storage = FakeObjectStorage()
    storage.inject_object(
        key=ordinary.object_key, content_type="application/pdf", size_bytes=1, sha256=SHA256,
    )
    storage.inject_object(
        key=reconciled.promotion_target_key,
        content_type="application/pdf", size_bytes=1, sha256=SHA256,
    )

    cleanup_expired(now=now, storage=storage, batch_size=1)
    import importlib
    import splitbind.retention.services as cleanup_module
    importlib.reload(cleanup_module)
    cleanup_module.cleanup_expired(
        now=now + timedelta(seconds=1), storage=storage, batch_size=1,
    )

    ordinary.refresh_from_db()
    reconciled.refresh_from_db()
    assert ordinary.orphan_deleted_at is not None
    assert reconciled.promotion_target_reconciled_at is not None
    assert ordinary.object_key not in storage.objects
    assert reconciled.promotion_target_key not in storage.objects


@pytest.mark.django_db
def test_ordinary_cleanup_is_not_starved_by_permanent_reconciliation_backlog():
    now = timezone.now()
    org = Organization.objects.create(name="Ordinary fair", slug=f"ordinary-fair-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(
        username="ordinary-fair", password="test", organization=org, role=Role.ISSUER,
    )
    ordinary = upload(org, actor, created_at=now - timedelta(hours=25))
    storage = FakeObjectStorage()
    storage.inject_object(
        key=ordinary.object_key, content_type="application/pdf", size_bytes=1, sha256=SHA256,
    )
    for index in range(4):
        record = upload(
            org, actor,
            created_at=now - STALE_COPYING_AGE - timedelta(minutes=index + 1),
            status=PromotionStatus.FAILED,
        )
        _set_promotion_tombstone(record, at=now - timedelta(minutes=index + 1))

    for index in range(2):
        cleanup_expired(
            now=now + timedelta(seconds=index), storage=storage, batch_size=1,
        )

    ordinary.refresh_from_db()
    assert ordinary.orphan_deleted_at is not None


@pytest.mark.django_db
def test_reconciliation_is_not_starved_by_permanent_ordinary_backlog():
    now = timezone.now()
    org = Organization.objects.create(name="Reconcile fair", slug=f"reconcile-fair-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(
        username="reconcile-fair", password="test", organization=org, role=Role.ISSUER,
    )
    reconciled = upload(
        org, actor, created_at=now - STALE_COPYING_AGE - timedelta(minutes=1),
        status=PromotionStatus.FAILED,
    )
    _set_promotion_tombstone(reconciled, at=now - timedelta(minutes=1))
    storage = FakeObjectStorage()
    storage.inject_object(
        key=reconciled.promotion_target_key,
        content_type="application/pdf", size_bytes=1, sha256=SHA256,
    )
    for index in range(4):
        record = upload(
            org, actor, created_at=now - timedelta(hours=25, minutes=index),
        )
        storage.inject_object(
            key=record.object_key,
            content_type="application/pdf", size_bytes=1, sha256=SHA256,
        )

    for index in range(2):
        cleanup_expired(
            now=now + timedelta(seconds=index), storage=storage, batch_size=1,
        )

    reconciled.refresh_from_db()
    assert reconciled.promotion_target_reconciled_at is not None
    assert reconciled.promotion_target_key not in storage.objects


@pytest.mark.django_db
def test_invalid_reconciliation_key_advances_fair_order_and_audits_safe_failure():
    now = timezone.now()
    org = Organization.objects.create(name="Invalid fair", slug=f"invalid-fair-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(
        username="invalid-fair", password="test", organization=org, role=Role.ISSUER,
    )
    invalid = upload(
        org, actor, created_at=now - STALE_COPYING_AGE - timedelta(minutes=2),
        status=PromotionStatus.FAILED,
    )
    valid = upload(
        org, actor, created_at=now - STALE_COPYING_AGE - timedelta(minutes=1),
        status=PromotionStatus.FAILED,
    )
    wrong_key = f"inputs/issuance/{org.id}/{uuid.uuid4()}.bin"
    _set_promotion_tombstone(invalid, at=now - timedelta(minutes=2), target_key=wrong_key)
    _set_promotion_tombstone(valid, at=now - timedelta(minutes=1))
    storage = FakeObjectStorage()
    storage.inject_object(
        key=valid.promotion_target_key,
        content_type="application/pdf", size_bytes=1, sha256=SHA256,
    )

    cleanup_expired(now=now, storage=storage, batch_size=1)
    schedule = CleanupScheduleState.objects.get(pk=1)
    assert schedule.reconciliation_cursor_id == invalid.id
    assert schedule.reconciliation_cursor_at == invalid.promotion_target_deleted_at
    cleanup_expired(now=now + timedelta(seconds=1), storage=storage, batch_size=1)
    schedule.refresh_from_db()
    assert schedule.reconciliation_cursor_id == valid.id

    invalid.refresh_from_db()
    valid.refresh_from_db()
    assert invalid.promotion_target_reconciled_at is not None
    assert valid.promotion_target_reconciled_at is not None
    assert valid.promotion_target_key not in storage.objects
    failure = AuditEvent.objects.get(
        action="object.promotion.reconciliation.failed", target_id=str(invalid.pk),
    )
    assert failure.metadata == {"safe_error_code": "INVALID_CONTROLLED_KEY"}


@pytest.mark.django_db
def test_new_invalid_tombstones_do_not_monopolize_reconciliation_order():
    now = timezone.now()
    org = Organization.objects.create(name="Cursor fair", slug=f"cursor-fair-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(
        username="cursor-fair", password="test", organization=org, role=Role.ISSUER,
    )
    first = upload(
        org, actor, created_at=now - STALE_COPYING_AGE - timedelta(minutes=3),
        status=PromotionStatus.FAILED,
        upload_id=uuid.UUID("00000000-0000-4000-8000-000000000001"),
    )
    valid = upload(
        org, actor, created_at=now - STALE_COPYING_AGE - timedelta(minutes=2),
        status=PromotionStatus.FAILED,
        upload_id=uuid.UUID("00000000-0000-4000-8000-000000000002"),
    )
    _set_promotion_tombstone(
        first, at=now - timedelta(minutes=3),
        target_key=f"inputs/issuance/{org.id}/{uuid.uuid4()}.bin",
    )
    _set_promotion_tombstone(valid, at=now - timedelta(minutes=2))
    storage = FakeObjectStorage()
    storage.inject_object(
        key=valid.promotion_target_key,
        content_type="application/pdf", size_bytes=1, sha256=SHA256,
    )

    cleanup_expired(now=now, storage=storage, batch_size=1)
    newcomer = upload(
        org, actor, created_at=now - STALE_COPYING_AGE - timedelta(minutes=1),
        status=PromotionStatus.FAILED,
        upload_id=uuid.UUID("00000000-0000-4000-8000-000000000000"),
    )
    _set_promotion_tombstone(
        newcomer, at=now - timedelta(minutes=1),
        target_key=f"inputs/issuance/{org.id}/{uuid.uuid4()}.bin",
    )
    cleanup_expired(now=now + timedelta(seconds=1), storage=storage, batch_size=1)

    first.refresh_from_db()
    valid.refresh_from_db()
    newcomer.refresh_from_db()
    assert first.promotion_target_reconciled_at is not None
    assert valid.promotion_target_reconciled_at is not None
    assert newcomer.promotion_target_reconciled_at is None
    assert valid.promotion_target_key not in storage.objects


@pytest.mark.django_db
def test_reconciliation_clamps_stale_requested_time_after_locked_observation():
    now = timezone.now()
    org = Organization.objects.create(name="Clamp observation", slug=f"clamp-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(
        username="clamp-observation", password="test", organization=org, role=Role.ISSUER,
    )
    record = upload(
        org, actor, created_at=now - STALE_COPYING_AGE - timedelta(minutes=1),
        status=PromotionStatus.FAILED,
    )
    _set_promotion_tombstone(record, at=now - timedelta(minutes=1))
    future = now + timedelta(minutes=5)
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE uploads_uploadrequest SET promotion_target_reconciled_at = %s WHERE id = %s",
            [future, record.id.hex],
        )

    assert cleanup_expired(now=now, storage=FakeObjectStorage(), batch_size=1) == 0
    record.refresh_from_db()
    assert record.promotion_target_reconciled_at == future


@pytest.mark.django_db
def test_reconciliation_samples_observation_time_after_acquiring_row_lock(monkeypatch):
    requested_at = timezone.now()
    locked_at = requested_at + timedelta(seconds=5)
    org = Organization.objects.create(name="Locked clock", slug=f"locked-clock-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(
        username="locked-clock", password="test", organization=org, role=Role.ISSUER,
    )
    record = upload(
        org, actor,
        created_at=requested_at - STALE_COPYING_AGE - timedelta(minutes=1),
        status=PromotionStatus.FAILED,
    )
    _set_promotion_tombstone(record, at=requested_at - timedelta(minutes=1))
    monkeypatch.setattr(retention_services.timezone, "now", lambda: locked_at)

    cleanup_expired(
        now=requested_at, storage=FakeObjectStorage(), batch_size=1,
    )

    record.refresh_from_db()
    assert record.promotion_target_reconciled_at == locked_at


@pytest.mark.django_db
@pytest.mark.parametrize("manager_name", ["objects", "_base_manager"])
@pytest.mark.parametrize("as_generator", [False, True])
def test_upload_conflict_upsert_cannot_rewrite_promotion_evidence(manager_name, as_generator):
    now = timezone.now()
    org = Organization.objects.create(name="Upload upsert", slug=f"upload-upsert-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(
        username="upload-upsert", password="test", organization=org, role=Role.ISSUER,
    )
    existing = upload(org, actor, created_at=now)
    conflict = UploadRequest(
        organization=org, requested_by=actor, purpose=existing.purpose,
        object_key=existing.object_key, expected_sha256=SHA256, size_bytes=1,
        expires_at=now + timedelta(minutes=15),
        promotion_status=PromotionStatus.COPYING,
        promotion_target_key=f"inputs/issuance/{org.id}/{uuid.uuid4()}.bin",
    )

    values = [conflict]
    values = (item for item in values) if as_generator else values
    manager = getattr(UploadRequest, manager_name)
    with pytest.raises(ValidationError, match="conflict"):
        manager.bulk_create(
            values, update_conflicts=True,
            update_fields=["promotion_status", "promotion_target_key"],
            unique_fields=["object_key"],
        )
    existing.refresh_from_db()
    assert existing.promotion_status == PromotionStatus.NONE
    assert UploadRequest.objects.count() == 1


@pytest.mark.django_db
def test_transient_cleanup_failure_retains_timestamp_and_writes_only_safe_audit():
    now = timezone.now()
    org = Organization.objects.create(name="Retry", slug=f"retry-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(username="retry-issuer", password="test", organization=org, role=Role.ISSUER)
    record = upload(org, actor, created_at=now - timedelta(hours=25))
    storage = FakeObjectStorage()
    storage.inject_object(key=record.object_key, content_type="application/pdf", size_bytes=1, sha256=SHA256)
    storage.fail_next("delete", "https://provider.invalid/private?token=secret")

    assert cleanup_expired(now=now, storage=storage, batch_size=1) == 0

    record.refresh_from_db()
    assert record.orphan_deleted_at is None
    event = AuditEvent.objects.latest("created_at")
    assert event.actor_id is None and event.outcome == AuditOutcome.FAILED
    assert event.metadata == {"safe_error_code": "STORAGE_DELETE_RETRY"}
    assert "provider" not in str(event.metadata)


@pytest.mark.django_db
@pytest.mark.parametrize("purpose", [UploadPurpose.ISSUANCE, UploadPurpose.VERIFICATION])
def test_attached_input_cleanup_uses_outcome_specific_window(purpose):
    now = timezone.now()
    org = Organization.objects.create(name="Attached", slug=f"attached-{purpose}-{uuid.uuid4().hex[:6]}")
    role = Role.ISSUER if purpose == UploadPurpose.ISSUANCE else Role.VERIFIER
    actor = User.objects.create_user(username=f"attached-{purpose}", password="test", organization=org, role=role)
    storage = FakeObjectStorage()
    record = upload(org, actor, created_at=now, status=PromotionStatus.NONE, purpose=purpose)
    storage.inject_object(key=record.object_key, content_type="application/pdf", size_bytes=1, sha256=SHA256)
    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr("splitbind.jobs.services.timezone.now", lambda: now)
        from django.test import override_settings
        with override_settings(SPLITBIND_OBJECT_STORAGE=storage):
            if purpose == UploadPurpose.ISSUANCE:
                recipient = Recipient.objects.create(organization=org, external_reference="R", display_name="Synthetic")
                domain, job = create_issuance(actor, recipient.id, record.id, uuid.uuid4())
                job.status = JobStatus.SUCCEEDED
                job.save(update_fields=["status", "updated_at"])
                job.__class__.objects.filter(pk=job.pk).update(updated_at=now - timedelta(days=8))
            else:
                domain, job = create_verification(actor, record.id, uuid.uuid4())
                job.__class__.objects.filter(pk=job.pk).update(
                    status=JobStatus.SUCCEEDED, updated_at=now - timedelta(hours=25),
                )

    record.refresh_from_db()
    assert record.promotion_target_key in storage.objects
    assert cleanup_expired(now=now, storage=storage, batch_size=10) == 1
    record.refresh_from_db()
    assert record.promotion_target_deleted_at is not None


@pytest.mark.django_db
def test_issuance_output_cleanup_is_bounded_and_preserves_key():
    now = timezone.now()
    org = Organization.objects.create(name="Output", slug=f"output-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(username="output-issuer", password="test", organization=org, role=Role.ISSUER)
    recipient = Recipient.objects.create(organization=org, external_reference="R", display_name="Synthetic")
    storage = FakeObjectStorage()
    record = upload(org, actor, created_at=now, status=PromotionStatus.NONE)
    storage.inject_object(key=record.object_key, content_type="application/pdf", size_bytes=1, sha256=SHA256)
    from django.test import override_settings
    with override_settings(SPLITBIND_OBJECT_STORAGE=storage):
        issuance, job = create_issuance(actor, recipient.id, record.id, uuid.uuid4())
    job.status = JobStatus.SUCCEEDED
    job.save(update_fields=["status", "updated_at"])
    job.__class__.objects.filter(pk=job.pk).update(updated_at=now - timedelta(days=31))
    record.refresh_from_db()
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE uploads_uploadrequest SET promotion_target_deleted_at = %s, "
            "promotion_target_reconciled_at = %s WHERE id = %s",
            [now, now, record.id.hex],
        )
    output_key = f"outputs/issuance/{org.id}/{issuance.id}.pdf"
    issuance.__class__.objects.filter(pk=issuance.pk).update(
        output_object_key=output_key, output_sha256=SHA256, issued_at=now - timedelta(days=31),
    )
    storage.inject_object(key=output_key, content_type="application/pdf", size_bytes=1, sha256=SHA256)

    newest = Job.objects.create(
        organization=org,
        kind=JobKind.ISSUANCE,
        status=JobStatus.PROCESSING,
        issuance=issuance,
        deadline_at=now + timedelta(minutes=10),
        correlation_id=uuid.uuid4(),
    )
    assert cleanup_expired(now=now, storage=storage, batch_size=1) == 0
    Job._base_manager.filter(pk=newest.pk).update(
        status=JobStatus.FAILED, updated_at=now - timedelta(minutes=1),
    )
    assert cleanup_expired(now=now, storage=storage, batch_size=1) == 0
    Job._base_manager.filter(pk=newest.pk).update(
        updated_at=now - timedelta(days=31),
    )
    assert cleanup_expired(now=now, storage=storage, batch_size=1) == 1

    issuance.refresh_from_db()
    assert issuance.output_deleted_at is not None
    assert issuance.output_object_key == output_key
    assert output_key not in storage.objects


@pytest.mark.django_db
def test_concurrent_skip_locked_candidate_is_ignored_without_aborting_batch(monkeypatch):
    class LockedAway:
        def get(self, **kwargs):
            raise UploadRequest.DoesNotExist

    monkeypatch.setattr(retention_services, "_locked", lambda queryset: LockedAway())

    assert retention_services._delete_one(
        model=UploadRequest,
        pk=uuid.uuid4(),
        key_field="object_key",
        timestamp_field="orphan_deleted_at",
        action="object.orphan.deleted",
        category="orphan",
        storage=FakeObjectStorage(),
        now=timezone.now(),
    ) is False


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("initial", "next_status"),
    [(PromotionStatus.FAILED, PromotionStatus.COPYING),
     (PromotionStatus.COPYING, PromotionStatus.ATTACHED)],
)
def test_cleanup_rechecks_promotion_state_under_lock_before_delete(monkeypatch, initial, next_status):
    now = timezone.now()
    org = Organization.objects.create(name="Race", slug=f"race-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(username=f"race-{initial}", password="test", organization=org, role=Role.ISSUER)
    record = upload(org, actor, created_at=now - STALE_COPYING_AGE - timedelta(minutes=1), status=initial)
    storage = FakeObjectStorage()
    storage.inject_object(key=record.promotion_target_key, content_type="application/pdf", size_bytes=1, sha256=SHA256)
    original_locked = retention_services._locked
    changed = False

    def racing_locked(queryset):
        locked = original_locked(queryset)
        class Racing:
            def get(self, **kwargs):
                nonlocal changed
                if not changed:
                    changed = True
                    current = UploadRequest.objects.get(pk=record.pk)
                    current.save_promotion(status=next_status, target_key=current.promotion_target_key, safe_error_code=None)
                return locked.get(**kwargs)
        return Racing()
    monkeypatch.setattr(retention_services, "_locked", racing_locked)

    assert cleanup_expired(now=now, storage=storage, batch_size=1) == 0
    assert record.promotion_target_key in storage.objects


@pytest.mark.django_db
@pytest.mark.parametrize("status", [
    JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.DEAD_LETTERED,
])
@pytest.mark.parametrize("purpose", [UploadPurpose.ISSUANCE, UploadPurpose.VERIFICATION])
def test_attached_inputs_expire_after_every_terminal_job_status(status, purpose):
    now = timezone.now()
    org = Organization.objects.create(name="Terminal", slug=f"terminal-{uuid.uuid4().hex[:8]}")
    role = Role.ISSUER if purpose == UploadPurpose.ISSUANCE else Role.VERIFIER
    actor = User.objects.create_user(username=f"terminal-{purpose}-{status}", password="test", organization=org, role=role)
    record = upload(org, actor, created_at=now, purpose=purpose)
    storage = FakeObjectStorage()
    storage.inject_object(key=record.object_key, content_type="application/pdf", size_bytes=1, sha256=SHA256)
    from django.test import override_settings
    with override_settings(SPLITBIND_OBJECT_STORAGE=storage):
        if purpose == UploadPurpose.ISSUANCE:
            recipient = Recipient.objects.create(organization=org, external_reference="R", display_name="Synthetic")
            _, job = create_issuance(actor, recipient.id, record.id, uuid.uuid4())
            age = timedelta(days=8)
        else:
            _, job = create_verification(actor, record.id, uuid.uuid4())
            age = timedelta(hours=25)
    job.__class__._base_manager.filter(pk=job.pk).update(status=status, updated_at=now - age)

    assert cleanup_expired(now=now, storage=storage, batch_size=10) == 1


@pytest.mark.django_db
@pytest.mark.parametrize("status", [JobStatus.CREATED, JobStatus.QUEUED, JobStatus.PROCESSING, JobStatus.RETRYABLE_FAILED])
def test_attached_input_is_retained_for_nonterminal_job(status):
    now = timezone.now()
    org = Organization.objects.create(name="Running", slug=f"running-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(username=f"running-{status}", password="test", organization=org, role=Role.ISSUER)
    recipient = Recipient.objects.create(organization=org, external_reference="R", display_name="Synthetic")
    record = upload(org, actor, created_at=now)
    storage = FakeObjectStorage()
    storage.inject_object(key=record.object_key, content_type="application/pdf", size_bytes=1, sha256=SHA256)
    from django.test import override_settings
    with override_settings(SPLITBIND_OBJECT_STORAGE=storage):
        _, job = create_issuance(actor, recipient.id, record.id, uuid.uuid4())
    job.__class__._base_manager.filter(pk=job.pk).update(status=status, updated_at=now - timedelta(days=8))

    assert cleanup_expired(now=now, storage=storage, batch_size=10) == 0


@pytest.mark.django_db
def test_cleanup_refuses_key_not_bound_to_exact_row_identity():
    now = timezone.now()
    org = Organization.objects.create(name="Binding", slug=f"binding-{uuid.uuid4().hex[:8]}")
    other = Organization.objects.create(name="Other", slug=f"other-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(username="binding", password="test", organization=org, role=Role.ISSUER)
    record = upload(org, actor, created_at=now - timedelta(hours=25))
    wrong = f"uploads/orphan/issuance_input/{other.id}/{uuid.uuid4().hex}.bin"
    UploadRequest._base_manager.model._meta  # prove model path while using SQL corruption below
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("UPDATE uploads_uploadrequest SET object_key = %s WHERE id = %s", [wrong, record.id.hex])
    storage = FakeObjectStorage()
    storage.inject_object(key=wrong, content_type="application/pdf", size_bytes=1, sha256=SHA256)

    assert cleanup_expired(now=now, storage=storage, batch_size=1) == 0
    assert wrong in storage.objects


@pytest.mark.django_db
def test_cleanup_refuses_orphan_key_with_different_upload_identity():
    now = timezone.now()
    org = Organization.objects.create(name="Orphan binding", slug=f"orphan-binding-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(username="orphan-binding", password="test", organization=org, role=Role.ISSUER)
    record = upload(org, actor, created_at=now - timedelta(hours=25))
    wrong = f"uploads/orphan/issuance_input/{org.id}/{uuid.uuid4().hex}.bin"
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("UPDATE uploads_uploadrequest SET object_key = %s WHERE id = %s", [wrong, record.id.hex])
    storage = FakeObjectStorage()
    storage.inject_object(key=wrong, content_type="application/pdf", size_bytes=1, sha256=SHA256)

    assert cleanup_expired(now=now, storage=storage, batch_size=1) == 0
    assert wrong in storage.objects


@pytest.mark.django_db
def test_cleanup_refuses_promoted_key_with_different_upload_identity():
    now = timezone.now()
    org = Organization.objects.create(name="Promoted binding", slug=f"promoted-binding-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(username="promoted-binding", password="test", organization=org, role=Role.ISSUER)
    record = upload(
        org, actor, created_at=now - STALE_COPYING_AGE - timedelta(minutes=1),
        status=PromotionStatus.FAILED,
    )
    wrong = f"inputs/issuance/{org.id}/{uuid.uuid4()}.bin"
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("UPDATE uploads_uploadrequest SET promotion_target_key = %s WHERE id = %s", [wrong, record.id.hex])
    storage = FakeObjectStorage()
    storage.inject_object(key=wrong, content_type="application/pdf", size_bytes=1, sha256=SHA256)

    assert cleanup_expired(now=now, storage=storage, batch_size=1) == 0
    assert wrong in storage.objects


@pytest.mark.django_db
def test_deletion_timestamps_require_retention_service_and_are_monotonic():
    now = timezone.now()
    org = Organization.objects.create(name="Evidence", slug=f"evidence-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(username="evidence", password="test", organization=org, role=Role.ISSUER)
    record = upload(org, actor, created_at=now - timedelta(hours=25))

    record.orphan_deleted_at = now
    with pytest.raises(ValidationError, match="retention"):
        record.save(update_fields=["orphan_deleted_at"])
    with pytest.raises(ValidationError, match="retention"):
        UploadRequest._base_manager.filter(pk=record.pk).update(orphan_deleted_at=now)

    forged = UploadRequest(
        organization=org,
        requested_by=actor,
        purpose=UploadPurpose.ISSUANCE,
        object_key=f"uploads/orphan/issuance_input/{org.id}/{uuid.uuid4().hex}.bin",
        expected_sha256=SHA256,
        size_bytes=1,
        expires_at=now,
        orphan_deleted_at=now,
    )
    with pytest.raises(ValidationError, match="retention"):
        UploadRequest._base_manager.bulk_create([forged])


@pytest.mark.django_db
def test_success_timestamp_and_audit_are_one_database_transaction(monkeypatch):
    now = timezone.now()
    org = Organization.objects.create(name="Audit coupling", slug=f"audit-coupling-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(username="audit-coupling", password="test", organization=org, role=Role.ISSUER)
    record = upload(org, actor, created_at=now - timedelta(hours=25))
    storage = FakeObjectStorage()
    storage.inject_object(key=record.object_key, content_type="application/pdf", size_bytes=1, sha256=SHA256)
    monkeypatch.setattr(
        retention_services,
        "record_system_event",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("audit unavailable")),
    )

    with pytest.raises(RuntimeError, match="audit unavailable"):
        cleanup_expired(now=now, storage=storage, batch_size=1)

    record.refresh_from_db()
    assert record.orphan_deleted_at is None
    assert record.object_key not in storage.objects

    unrelated = upload(org, actor, created_at=now - timedelta(hours=23))
    storage.inject_object(
        key=unrelated.object_key, content_type="application/pdf", size_bytes=1, sha256=SHA256,
    )
    monkeypatch.undo()

    assert cleanup_expired(now=now, storage=storage, batch_size=1) == 1
    record.refresh_from_db()
    assert record.orphan_deleted_at is not None
    assert record.object_key not in storage.objects
    assert unrelated.object_key in storage.objects
    assert AuditEvent.objects.filter(
        action="object.orphan.deleted", target_id=str(record.id), outcome=AuditOutcome.SUCCEEDED,
    ).count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("purpose", [UploadPurpose.ISSUANCE, UploadPurpose.VERIFICATION])
def test_attached_cleanup_waits_for_all_jobs_and_uses_latest_terminal_time(purpose):
    now = timezone.now()
    org = Organization.objects.create(name="Latest terminal", slug=f"latest-terminal-{purpose}-{uuid.uuid4().hex[:6]}")
    role = Role.ISSUER if purpose == UploadPurpose.ISSUANCE else Role.VERIFIER
    actor = User.objects.create_user(username=f"latest-terminal-{purpose}", password="test", organization=org, role=role)
    record = upload(org, actor, created_at=now, purpose=purpose)
    storage = FakeObjectStorage()
    storage.inject_object(key=record.object_key, content_type="application/pdf", size_bytes=1, sha256=SHA256)
    from django.test import override_settings
    with override_settings(SPLITBIND_OBJECT_STORAGE=storage):
        if purpose == UploadPurpose.ISSUANCE:
            recipient = Recipient.objects.create(organization=org, external_reference="latest", display_name="Synthetic")
            domain, old_job = create_issuance(actor, recipient.id, record.id, uuid.uuid4())
            age = timedelta(days=8)
            kind = JobKind.ISSUANCE
        else:
            domain, old_job = create_verification(actor, record.id, uuid.uuid4())
            age = timedelta(hours=25)
            kind = JobKind.VERIFICATION
    Job._base_manager.filter(pk=old_job.pk).update(
        status=JobStatus.SUCCEEDED, updated_at=now - age,
    )
    new_job = Job.objects.create(
        organization=org,
        kind=kind,
        status=JobStatus.PROCESSING,
        issuance=domain if purpose == UploadPurpose.ISSUANCE else None,
        verification=domain if purpose == UploadPurpose.VERIFICATION else None,
        deadline_at=now + timedelta(minutes=10),
        correlation_id=uuid.uuid4(),
    )

    assert cleanup_expired(now=now, storage=storage, batch_size=10) == 0
    Job._base_manager.filter(pk=new_job.pk).update(
        status=JobStatus.FAILED, updated_at=now - timedelta(minutes=1),
    )
    assert cleanup_expired(now=now, storage=storage, batch_size=10) == 0
    Job._base_manager.filter(pk=new_job.pk).update(
        updated_at=now - age,
    )
    assert cleanup_expired(now=now, storage=storage, batch_size=10) == 1


@pytest.mark.django_db
def test_issuance_deletion_evidence_cannot_be_forged_with_bulk_create():
    now = timezone.now()
    org = Organization.objects.create(name="Output evidence", slug=f"output-evidence-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(username="output-evidence", password="test", organization=org, role=Role.ISSUER)
    source = upload(org, actor, created_at=now)
    document = Document.objects.create(
        organization=org, created_by=actor, upload_request=source,
        source_object_key=f"inputs/issuance/{org.id}/{source.id}.bin",
        expected_source_sha256=SHA256,
    )
    recipient = Recipient.objects.create(organization=org, external_reference="bulk", display_name="Synthetic")
    forged = Issuance(
        organization=org, document=document, recipient=recipient, created_by=actor,
        output_object_key=f"outputs/issuance/{org.id}/{uuid.uuid4()}.pdf",
        output_sha256=SHA256, output_deleted_at=now,
    )

    with pytest.raises(ValidationError, match="retention"):
        Issuance._base_manager.bulk_create([forged])


class PromotionRetentionConcurrencyContractTests(TransactionTestCase):
    def test_committed_retry_transition_wins_over_stale_cleanup_candidate(self):
        if connection.vendor != "postgresql":
            self.skipTest(
                "SQLite cannot verify cross-transaction row-lock ordering; PostgreSQL runtime remains the P3 gate"
            )
        now = timezone.now()
        org = Organization.objects.create(name="Promotion race", slug=f"promotion-race-{uuid.uuid4().hex[:8]}")
        actor = User.objects.create_user(username="promotion-race", password="test", organization=org, role=Role.ISSUER)
        record = upload(
            org, actor, created_at=now - STALE_COPYING_AGE - timedelta(minutes=1),
            status=PromotionStatus.FAILED,
        )
        storage = FakeObjectStorage()
        storage.inject_object(
            key=record.promotion_target_key,
            content_type="application/pdf",
            size_bytes=1,
            sha256=SHA256,
        )
        transition_committed = threading.Event()
        errors = []

        def retry_transition():
            close_old_connections()
            try:
                current = UploadRequest.objects.get(pk=record.pk)
                current.save_promotion(
                    status=PromotionStatus.COPYING,
                    target_key=current.promotion_target_key,
                    safe_error_code=None,
                )
            except Exception as error:
                errors.append(error)
            finally:
                close_old_connections()
                transition_committed.set()

        thread = threading.Thread(target=retry_transition)
        thread.start()
        assert transition_committed.wait(timeout=5)
        assert cleanup_expired(now=now, storage=storage, batch_size=1) == 0
        thread.join(timeout=5)

        record.refresh_from_db()
        assert errors == []
        assert not thread.is_alive()
        assert record.promotion_status == PromotionStatus.COPYING
        assert record.promotion_target_deleted_at is None
        assert record.promotion_target_key in storage.objects
