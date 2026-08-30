import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from splitbind.access.models import Organization, Role, User
from splitbind.access.models import Recipient
from splitbind.audit.models import AuditEvent, AuditOutcome
from splitbind.integrations.storage.fake import FakeObjectStorage
from splitbind.jobs.models import JobStatus
from splitbind.jobs.services import create_issuance, create_verification
from splitbind.documents.models import Document, Issuance
from splitbind.retention.services import STALE_COPYING_AGE, cleanup_expired
from splitbind.retention import services as retention_services
from splitbind.uploads.models import PromotionStatus, UploadPurpose, UploadRequest
from django.core.exceptions import ValidationError


SHA256 = "a" * 64


def upload(org, actor, *, created_at, status=PromotionStatus.NONE, purpose=UploadPurpose.ISSUANCE):
    kind = "issuance_input" if purpose == UploadPurpose.ISSUANCE else "verification_input"
    upload_id = uuid.uuid4()
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
        record.save_promotion(status=PromotionStatus.COPYING, target_key=target, safe_error_code=None)
        if status == PromotionStatus.FAILED:
            record.save_promotion(status=PromotionStatus.FAILED, target_key=target, safe_error_code="PROMOTION_COPY_FAILED")
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
            "UPDATE uploads_uploadrequest SET promotion_target_deleted_at = %s WHERE id = %s",
            [now, record.id.hex],
        )
    output_key = f"outputs/issuance/{org.id}/{issuance.id}.pdf"
    issuance.__class__.objects.filter(pk=issuance.pk).update(
        output_object_key=output_key, output_sha256=SHA256, issued_at=now - timedelta(days=31),
    )
    storage.inject_object(key=output_key, content_type="application/pdf", size_bytes=1, sha256=SHA256)

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
