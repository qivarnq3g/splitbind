import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from splitbind.audit.models import AuditEvent, AuditOutcome
from splitbind.audit.services import record_event, record_system_event
from splitbind.documents.models import Issuance
from splitbind.integrations.storage.base import (
    validate_issuance_output_key, validate_orphan_key, validate_promoted_key,
)
from splitbind.jobs.models import Job, JobStatus
from splitbind.retention.capabilities import (
    _allow_cleanup_schedule_write, _allow_deletion_evidence_write,
)
from splitbind.retention.policies import retention_deadline
from splitbind.uploads.models import (
    CleanupLane, CleanupScheduleState, PromotionStatus, UploadPurpose,
    UploadRequest,
)
from splitbind.uploads.services import get_storage


STALE_COPYING_AGE = timedelta(hours=1)
DEFAULT_BATCH_SIZE = 100
MAX_BATCH_SIZE = 500
TERMINAL_JOB_STATUSES = {
    JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED, JobStatus.DEAD_LETTERED,
}


def _window(kind, now):
    return retention_deadline(kind, now) - now


def _locked(queryset):
    if connection.features.has_select_for_update_skip_locked:
        return queryset.select_for_update(skip_locked=True)
    return queryset.select_for_update()


def _audit_failure(record, action):
    try:
        record_system_event(
            record.organization, action, record, AuditOutcome.FAILED, uuid.uuid4(),
            {"safe_error_code": "STORAGE_DELETE_RETRY"},
        )
    except Exception:
        pass


def _record_deletion_evidence(
    record, *, timestamp_field, action, at, correlation_id, actor=None,
):
    """Persist one monotonic deletion fact and its audit in one transaction.

    Callers must already have deleted the exact controlled object and hold (or
    acquire in their surrounding transaction) the applicable row lock.
    """
    allowed = {
        UploadRequest: {"orphan_deleted_at", "promotion_target_deleted_at"},
        Issuance: {"output_deleted_at"},
    }
    if type(record) not in allowed or timestamp_field not in allowed[type(record)]:
        raise ValueError("deletion evidence target is invalid")
    if timezone.is_naive(at):
        raise ValueError("deletion evidence time must be timezone-aware")
    with transaction.atomic():
        if getattr(record, timestamp_field) is not None:
            return False
        setattr(record, timestamp_field, at)
        with _allow_deletion_evidence_write():
            record.save(update_fields=[timestamp_field])
        if actor is None:
            record_system_event(
                record.organization, action, record, AuditOutcome.SUCCEEDED,
                correlation_id, {"status": "deleted"},
            )
        else:
            record_event(
                actor, action, record, AuditOutcome.SUCCEEDED,
                correlation_id, {"status": "deleted"},
            )
        return True


def _record_promotion_reconciliation(
    record, *, at, succeeded, safe_error_code="STORAGE_DELETE_RETRY",
):
    """Persist one reconciliation observation and at most one audit per outcome."""
    previous = record.promotion_target_reconciled_at
    if previous is not None and at < previous:
        at = previous
    record.promotion_target_reconciled_at = at
    with _allow_deletion_evidence_write():
        record.save(update_fields=["promotion_target_reconciled_at"])
    outcome = AuditOutcome.SUCCEEDED if succeeded else AuditOutcome.FAILED
    action = f"object.promotion.reconciliation.{outcome}"
    already_reported = AuditEvent.objects.filter(
        organization_id=record.organization_id,
        action=action,
        target_type=record._meta.label_lower,
        target_id=str(record.pk),
        outcome=outcome,
    ).exists()
    if not already_reported:
        metadata = (
            {"status": "deleted"}
            if succeeded
            else {"safe_error_code": safe_error_code}
        )
        record_system_event(
            record.organization, action, record, outcome, uuid.uuid4(), metadata,
        )


@dataclass(frozen=True)
class ReconciliationClaim:
    upload_id: uuid.UUID
    token: uuid.UUID


@dataclass(frozen=True)
class ReconciliationAttempt:
    succeeded: bool
    acknowledge: bool
    safe_error_code: str | None = None


def delete_attached_orphan_source(
    *, upload_id, storage, actor, correlation_id, at=None,
):
    """Delete one just-attached orphan source and atomically retain evidence."""
    at = at or timezone.now()
    with transaction.atomic():
        record = UploadRequest.objects.select_for_update().select_related("organization").get(
            pk=upload_id,
            organization_id=actor.organization_id,
            requested_by_id=actor.id,
        )
        if record.orphan_deleted_at is not None:
            return False
        if record.promotion_status != PromotionStatus.ATTACHED:
            raise ValueError("orphan cleanup ownership state is invalid")
        if not _key_is_owned(record, "orphan", record.object_key):
            raise ValueError("orphan cleanup key ownership is invalid")
        storage.delete(key=record.object_key)
        return _record_deletion_evidence(
            record,
            timestamp_field="orphan_deleted_at",
            action="object.orphan.deleted",
            at=at,
            correlation_id=correlation_id,
            actor=actor,
        )


def delete_fenced_promotion_target(*, upload_id, storage) -> bool:
    """Remove a target recreated after its durable cleanup tombstone.

    The tombstone is never cleared. Recovery requires a new upload/reservation;
    this path only restores the exact physical deletion already evidenced.
    """
    with transaction.atomic():
        record = UploadRequest.objects.select_for_update().get(pk=upload_id)
        if record.promotion_target_deleted_at is None:
            return False
        key = record.promotion_target_key
        if not key or not _key_is_owned(record, "stale_promotion", key):
            return False
        storage.delete(key=key)
        return True


def _key_is_owned(record, category, key):
    try:
        if category == "orphan":
            match = validate_orphan_key(key)
            expected = "issuance_input" if record.purpose == UploadPurpose.ISSUANCE else "verification_input"
            return (
                match.group(1) == expected
                and match.group("organization") == str(record.organization_id)
                and match.group("object") == record.id.hex
            )
        if category in {"stale_promotion", "issuance_input", "verification_input"}:
            match = validate_promoted_key(key)
            return (
                match.group("organization") == str(record.organization_id)
                and match.group("upload") == str(record.id)
                and match.group("kind") == record.purpose
            )
        if category == "issuance_output":
            match = validate_issuance_output_key(key)
            return (
                match.group("organization") == str(record.organization_id)
                and match.group("issuance") == str(record.id)
            )
    except ValueError:
        return False
    return False


def _related_jobs(record, category):
    if category == "issuance_input":
        return Job._base_manager.filter(issuance__document__upload_request_id=record.pk)
    if category == "verification_input":
        return Job._base_manager.filter(verification__upload_request_id=record.pk)
    if category == "issuance_output":
        return Job._base_manager.filter(issuance_id=record.pk)
    return Job._base_manager.none()


def _all_jobs_terminal_before(record, category, deadline):
    jobs = _related_jobs(record, category)
    if not jobs.exists() or jobs.exclude(status__in=TERMINAL_JOB_STATUSES).exists():
        return False
    if category == "issuance_output" and not jobs.filter(status=JobStatus.SUCCEEDED).exists():
        return False
    latest = jobs.order_by("-updated_at").values_list("updated_at", flat=True).first()
    return latest is not None and latest <= deadline


def _eligible_locked(record, category, now, expected_state=None):
    if category == "stale_promotion":
        return (
            record.promotion_status == expected_state
            and expected_state in {PromotionStatus.FAILED, PromotionStatus.COPYING}
            and record.promotion_status_changed_at <= now - STALE_COPYING_AGE
        )
    if category == "issuance_input":
        return (
            record.promotion_status == PromotionStatus.ATTACHED
            and record.purpose == UploadPurpose.ISSUANCE
            and _all_jobs_terminal_before(record, category, now - _window("issuance_input", now))
        )
    if category == "verification_input":
        return (
            record.promotion_status == PromotionStatus.ATTACHED
            and record.purpose == UploadPurpose.VERIFICATION
            and _all_jobs_terminal_before(record, category, now - _window("verification_input", now))
        )
    if category == "issuance_output":
        return _all_jobs_terminal_before(record, category, now - _window("issuance_output", now))
    if category == "orphan":
        return record.created_at <= now - _window("orphan_upload", now)
    return False


def _delete_one(*, model, pk, key_field, timestamp_field, action, category,
                storage, now, expected_state=None) -> bool:
    with transaction.atomic():
        try:
            record = _locked(model._base_manager.select_related("organization")).get(pk=pk)
        except model.DoesNotExist:
            return False
        if getattr(record, timestamp_field) is not None or not _eligible_locked(
            record, category, now, expected_state,
        ):
            return False
        key = getattr(record, key_field)
        if not key or not _key_is_owned(record, category, key):
            return False
        try:
            storage.delete(key=key)
        except Exception:
            _audit_failure(record, action + ".failed")
            return False
        return _record_deletion_evidence(
            record, timestamp_field=timestamp_field, action=action, at=now,
            correlation_id=uuid.uuid4(),
        )


def _ordinary_candidates(*, now, limit, excluded_ids):
    candidates = []

    def add(queryset, model, key_field, timestamp_field, action, category,
            order_field="created_at", expected_state=None):
        remaining = limit - len(candidates)
        if remaining <= 0:
            return
        excluded_pks = [
            pk for candidate_model, pk, candidate_timestamp_field in excluded_ids
            if candidate_model is model and candidate_timestamp_field == timestamp_field
        ]
        if excluded_pks:
            queryset = queryset.exclude(pk__in=excluded_pks)
        for pk in queryset.order_by(order_field, "pk").values_list("pk", flat=True)[:remaining]:
            candidates.append(
                (model, pk, key_field, timestamp_field, action, category, expected_state)
            )

    stale = now - STALE_COPYING_AGE
    terminal = list(TERMINAL_JOB_STATUSES)
    nonterminal = list(set(JobStatus.values) - TERMINAL_JOB_STATUSES)
    for state in (PromotionStatus.FAILED, PromotionStatus.COPYING):
        add(UploadRequest._base_manager.filter(
            promotion_status=state, promotion_target_deleted_at__isnull=True,
            promotion_target_key__isnull=False, promotion_status_changed_at__lte=stale,
        ), UploadRequest, "promotion_target_key", "promotion_target_deleted_at",
            "object.promotion.deleted", "stale_promotion", expected_state=state)
    issuance_deadline = now - _window("issuance_input", now)
    issuance_jobs = Job._base_manager.filter(
        issuance__document__upload_request_id=OuterRef("pk"),
    )
    add(UploadRequest._base_manager.filter(
        promotion_status=PromotionStatus.ATTACHED, promotion_target_deleted_at__isnull=True,
        purpose=UploadPurpose.ISSUANCE,
    ).annotate(
        has_terminal=Exists(issuance_jobs.filter(status__in=terminal)),
        has_nonterminal=Exists(issuance_jobs.filter(status__in=nonterminal)),
        has_recent_terminal=Exists(
            issuance_jobs.filter(status__in=terminal, updated_at__gt=issuance_deadline)
        ),
    ).filter(
        has_terminal=True, has_nonterminal=False, has_recent_terminal=False,
    ), UploadRequest, "promotion_target_key", "promotion_target_deleted_at",
        "object.issuance_input.deleted", "issuance_input")
    verification_deadline = now - _window("verification_input", now)
    verification_jobs = Job._base_manager.filter(
        verification__upload_request_id=OuterRef("pk"),
    )
    add(UploadRequest._base_manager.filter(
        promotion_status=PromotionStatus.ATTACHED, promotion_target_deleted_at__isnull=True,
        purpose=UploadPurpose.VERIFICATION,
    ).annotate(
        has_terminal=Exists(verification_jobs.filter(status__in=terminal)),
        has_nonterminal=Exists(verification_jobs.filter(status__in=nonterminal)),
        has_recent_terminal=Exists(
            verification_jobs.filter(status__in=terminal, updated_at__gt=verification_deadline)
        ),
    ).filter(
        has_terminal=True, has_nonterminal=False, has_recent_terminal=False,
    ), UploadRequest, "promotion_target_key", "promotion_target_deleted_at",
        "object.verification_input.deleted", "verification_input")
    output_deadline = now - _window("issuance_output", now)
    output_jobs = Job._base_manager.filter(issuance_id=OuterRef("pk"))
    add(Issuance._base_manager.filter(
        output_deleted_at__isnull=True, output_object_key__isnull=False,
    ).annotate(
        has_success=Exists(output_jobs.filter(status=JobStatus.SUCCEEDED)),
        has_nonterminal=Exists(output_jobs.filter(status__in=nonterminal)),
        has_recent_terminal=Exists(
            output_jobs.filter(status__in=terminal, updated_at__gt=output_deadline)
        ),
    ).filter(
        has_success=True, has_nonterminal=False, has_recent_terminal=False,
    ), Issuance, "output_object_key", "output_deleted_at",
        "object.issuance_output.deleted", "issuance_output", "issued_at")
    add(UploadRequest._base_manager.filter(
        orphan_deleted_at__isnull=True, created_at__lte=now - _window("orphan_upload", now),
    ), UploadRequest, "object_key", "orphan_deleted_at", "object.orphan.deleted", "orphan")
    return candidates


def _next_reconciliation_candidate(schedule, *, excluded_ids):
    queryset = UploadRequest._base_manager.filter(
        promotion_target_deleted_at__isnull=False,
        promotion_target_key__isnull=False,
    ).exclude(pk__in=excluded_ids)
    if (
        schedule.reconciliation_cursor_at is not None
        and schedule.reconciliation_cursor_id is not None
    ):
        after_cursor = queryset.filter(
            Q(promotion_target_deleted_at__gt=schedule.reconciliation_cursor_at)
            | Q(
                promotion_target_deleted_at=schedule.reconciliation_cursor_at,
                pk__gt=schedule.reconciliation_cursor_id,
            )
        )
        candidate = after_cursor.order_by(
            "promotion_target_deleted_at", "pk",
        ).values_list("pk", "promotion_target_deleted_at").first()
        if candidate is not None:
            return candidate
    return queryset.order_by(
        "promotion_target_deleted_at", "pk",
    ).values_list("pk", "promotion_target_deleted_at").first()


def _save_schedule(schedule):
    with _allow_cleanup_schedule_write():
        schedule.save()


def _clear_claim(schedule):
    schedule.reconciliation_claim_upload_id = None
    schedule.reconciliation_claim_token = None
    schedule.reconciliation_claim_expires_at = None


def _claim_reconciliation(*, now):
    """Persist one leased claim without moving the acknowledged cursor."""
    with transaction.atomic():
        schedule = CleanupScheduleState.objects.select_for_update().get(pk=1)
        locked_now = max(now, timezone.now())
        upload_id = schedule.reconciliation_claim_upload_id
        if upload_id is not None:
            if schedule.reconciliation_claim_expires_at > locked_now:
                return None
        else:
            selected = _next_reconciliation_candidate(schedule, excluded_ids=set())
            if selected is None:
                return None
            upload_id, _ = selected

        try:
            record = UploadRequest._base_manager.select_for_update().get(pk=upload_id)
        except UploadRequest.DoesNotExist:
            _clear_claim(schedule)
            _save_schedule(schedule)
            return None
        if record.promotion_target_deleted_at is None:
            _clear_claim(schedule)
            _save_schedule(schedule)
            return None

        token = uuid.uuid4()
        schedule.reconciliation_claim_upload_id = record.pk
        schedule.reconciliation_claim_token = token
        schedule.reconciliation_claim_expires_at = locked_now + timedelta(
            seconds=settings.RETENTION_RECONCILIATION_LEASE_SECONDS,
        )
        schedule.has_run = True
        _save_schedule(schedule)
        return ReconciliationClaim(upload_id=record.pk, token=token)


def _attempt_reconciliation(*, claim, storage):
    """Attempt exact-key deletion without holding the scheduler row lock."""
    try:
        record = UploadRequest._base_manager.get(pk=claim.upload_id)
    except UploadRequest.DoesNotExist:
        return ReconciliationAttempt(False, True, "MISSING_CLEANUP_OWNER")
    if record.promotion_target_deleted_at is None:
        return ReconciliationAttempt(False, True, "INELIGIBLE_CLEANUP_OWNER")
    key = record.promotion_target_key
    if not key or not _key_is_owned(record, "stale_promotion", key):
        return ReconciliationAttempt(False, True, "INVALID_CONTROLLED_KEY")
    try:
        storage.delete(key=key)
    except Exception:
        return ReconciliationAttempt(False, False, "STORAGE_DELETE_RETRY")
    return ReconciliationAttempt(True, True)


def _claim_matches(schedule, claim):
    return (
        schedule.reconciliation_claim_upload_id == claim.upload_id
        and schedule.reconciliation_claim_token == claim.token
    )


def _ack_reconciliation(*, claim, at, succeeded, safe_error_code=None):
    """Record an attempted outcome and advance only the matching claim token."""
    with transaction.atomic():
        schedule = CleanupScheduleState.objects.select_for_update().get(pk=1)
        if not _claim_matches(schedule, claim):
            return False
        try:
            record = UploadRequest._base_manager.select_for_update().select_related(
                "organization",
            ).get(pk=claim.upload_id)
        except UploadRequest.DoesNotExist:
            _clear_claim(schedule)
            _save_schedule(schedule)
            return False
        if record.promotion_target_deleted_at is None:
            _clear_claim(schedule)
            _save_schedule(schedule)
            return False
        observed_at = max(
            at, timezone.now(), record.promotion_target_reconciled_at or at,
        )
        _record_promotion_reconciliation(
            record, at=observed_at, succeeded=succeeded,
            safe_error_code=safe_error_code or "STORAGE_DELETE_RETRY",
        )
        schedule.reconciliation_cursor_at = record.promotion_target_deleted_at
        schedule.reconciliation_cursor_id = record.pk
        _clear_claim(schedule)
        schedule.next_lane = CleanupLane.ORDINARY
        schedule.has_run = True
        _save_schedule(schedule)
        return True


def _record_claim_retry(*, claim, at, safe_error_code):
    """Persist retry evidence while retaining claim ownership and cursor."""
    with transaction.atomic():
        schedule = CleanupScheduleState.objects.select_for_update().get(pk=1)
        if not _claim_matches(schedule, claim):
            return False
        try:
            record = UploadRequest._base_manager.select_for_update().select_related(
                "organization",
            ).get(pk=claim.upload_id)
        except UploadRequest.DoesNotExist:
            _clear_claim(schedule)
            _save_schedule(schedule)
            return False
        if record.promotion_target_deleted_at is None:
            _clear_claim(schedule)
            _save_schedule(schedule)
            return False
        observed_at = max(
            at, timezone.now(), record.promotion_target_reconciled_at or at,
        )
        _record_promotion_reconciliation(
            record, at=observed_at, succeeded=False,
            safe_error_code=safe_error_code,
        )
        schedule.next_lane = CleanupLane.ORDINARY
        schedule.has_run = True
        _save_schedule(schedule)
        return True


def _preferred_lane():
    with transaction.atomic():
        return CleanupScheduleState.objects.select_for_update().get(pk=1).next_lane


def _mark_ordinary_attempt():
    with transaction.atomic():
        schedule = CleanupScheduleState.objects.select_for_update().get(pk=1)
        schedule.next_lane = CleanupLane.RECONCILIATION
        schedule.has_run = True
        _save_schedule(schedule)


def _run_ordinary_once(*, now, storage, attempted_ids):
    candidates = _ordinary_candidates(
        now=now, limit=1, excluded_ids=attempted_ids,
    )
    if not candidates:
        return None
    model, pk, key_field, timestamp_field, action, category, expected_state = candidates[0]
    attempted_ids.add((model, pk, timestamp_field))
    completed = _delete_one(
        model=model, pk=pk, key_field=key_field,
        timestamp_field=timestamp_field, action=action,
        category=category, expected_state=expected_state,
        storage=storage, now=now,
    )
    _mark_ordinary_attempt()
    return completed


def _run_reconciliation_once(*, now, storage):
    claim = _claim_reconciliation(now=now)
    if claim is None:
        return False
    attempt = _attempt_reconciliation(claim=claim, storage=storage)
    if attempt.acknowledge:
        _ack_reconciliation(
            claim=claim, at=now, succeeded=attempt.succeeded,
            safe_error_code=attempt.safe_error_code,
        )
    else:
        _record_claim_retry(
            claim=claim, at=now,
            safe_error_code=attempt.safe_error_code or "STORAGE_DELETE_RETRY",
        )
    return True


def cleanup_expired(*, now=None, storage=None, batch_size=DEFAULT_BATCH_SIZE) -> int:
    now = now or timezone.now()
    if timezone.is_naive(now):
        raise ValueError("cleanup time must be timezone-aware")
    if not isinstance(batch_size, int) or isinstance(batch_size, bool) or not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise ValueError("cleanup batch size is invalid")
    storage = storage or get_storage()
    deleted = 0
    ordinary_attempted_ids = set()
    for _ in range(batch_size):
        preferred = _preferred_lane()
        if preferred == CleanupLane.ORDINARY:
            completed = _run_ordinary_once(
                now=now, storage=storage, attempted_ids=ordinary_attempted_ids,
            )
            if completed is not None:
                deleted += int(completed)
                continue
            if _run_reconciliation_once(now=now, storage=storage):
                continue
        else:
            if _run_reconciliation_once(now=now, storage=storage):
                continue
            completed = _run_ordinary_once(
                now=now, storage=storage, attempted_ids=ordinary_attempted_ids,
            )
            if completed is not None:
                deleted += int(completed)
                continue
        break
    return deleted
