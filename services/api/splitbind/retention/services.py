import uuid
from datetime import timedelta

from django.db import connection, transaction
from django.utils import timezone

from splitbind.audit.models import AuditOutcome
from splitbind.audit.services import record_system_event
from splitbind.documents.models import Issuance
from splitbind.jobs.models import JobStatus
from splitbind.uploads.models import PromotionStatus, UploadRequest
from splitbind.uploads.services import get_storage


STALE_COPYING_AGE = timedelta(hours=1)
DEFAULT_BATCH_SIZE = 100
MAX_BATCH_SIZE = 500


def _locked(queryset):
    if connection.features.has_select_for_update_skip_locked:
        return queryset.select_for_update(skip_locked=True)
    return queryset.select_for_update()


def _audit_failure(record, action):
    try:
        record_system_event(
            record.organization,
            action,
            record,
            AuditOutcome.FAILED,
            uuid.uuid4(),
            {"safe_error_code": "STORAGE_DELETE_RETRY"},
        )
    except Exception:
        pass


def _delete_one(*, model, pk, key_field, timestamp_field, action, storage, now) -> bool:
    with transaction.atomic():
        try:
            record = _locked(model._base_manager.select_related("organization")).get(pk=pk)
        except model.DoesNotExist:
            return False
        if getattr(record, timestamp_field) is not None:
            return False
        key = getattr(record, key_field)
        if not key:
            return False
        try:
            storage.delete(key=key)
        except Exception:
            _audit_failure(record, action + ".failed")
            return False
        setattr(record, timestamp_field, now)
        record.save(update_fields=[timestamp_field])
        record_system_event(
            record.organization,
            action,
            record,
            AuditOutcome.SUCCEEDED,
            uuid.uuid4(),
            {"status": "deleted"},
        )
        return True


def cleanup_expired(*, now=None, storage=None, batch_size=DEFAULT_BATCH_SIZE) -> int:
    """Delete exact owned keys in a bounded, retryable, idempotent batch."""
    now = now or timezone.now()
    if timezone.is_naive(now):
        raise ValueError("cleanup time must be timezone-aware")
    if not isinstance(batch_size, int) or isinstance(batch_size, bool) or not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise ValueError("cleanup batch size is invalid")
    storage = storage or get_storage()
    candidates: list[tuple[object, object, str, str, str]] = []

    def add(queryset, model, key_field, timestamp_field, action, order_field="created_at"):
        remaining = batch_size - len(candidates)
        if remaining <= 0:
            return
        for pk in queryset.order_by(order_field, "pk").values_list("pk", flat=True)[:remaining]:
            candidates.append((model, pk, key_field, timestamp_field, action))

    stale = now - STALE_COPYING_AGE
    add(
        UploadRequest._base_manager.filter(
            promotion_status__in=[PromotionStatus.FAILED, PromotionStatus.COPYING],
            promotion_target_deleted_at__isnull=True,
            promotion_target_key__isnull=False,
            created_at__lte=stale,
        ),
        UploadRequest, "promotion_target_key", "promotion_target_deleted_at", "object.promotion.deleted",
    )
    add(
        UploadRequest._base_manager.filter(
            promotion_status=PromotionStatus.ATTACHED,
            promotion_target_deleted_at__isnull=True,
            purpose="issuance",
            document__issuances__jobs__status=JobStatus.SUCCEEDED,
            document__issuances__jobs__updated_at__lte=now - timedelta(days=7),
        ).distinct(),
        UploadRequest, "promotion_target_key", "promotion_target_deleted_at", "object.issuance_input.deleted",
    )
    add(
        UploadRequest._base_manager.filter(
            promotion_status=PromotionStatus.ATTACHED,
            promotion_target_deleted_at__isnull=True,
            purpose="verification",
            verification__completed_at__isnull=False,
            verification__completed_at__lte=now - timedelta(hours=24),
        ),
        UploadRequest, "promotion_target_key", "promotion_target_deleted_at", "object.verification_input.deleted",
    )
    add(
        Issuance._base_manager.filter(
            output_deleted_at__isnull=True,
            output_object_key__isnull=False,
            jobs__status=JobStatus.SUCCEEDED,
            jobs__updated_at__lte=now - timedelta(days=30),
        ).distinct(),
        Issuance, "output_object_key", "output_deleted_at", "object.issuance_output.deleted",
        "issued_at",
    )
    add(
        UploadRequest._base_manager.filter(
            orphan_deleted_at__isnull=True,
            created_at__lte=now - timedelta(hours=24),
        ),
        UploadRequest, "object_key", "orphan_deleted_at", "object.orphan.deleted",
    )

    deleted = 0
    for model, pk, key_field, timestamp_field, action in candidates:
        if _delete_one(
            model=model, pk=pk, key_field=key_field, timestamp_field=timestamp_field,
            action=action, storage=storage, now=now,
        ):
            deleted += 1
    return deleted
