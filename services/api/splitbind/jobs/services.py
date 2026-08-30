from datetime import timedelta

from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from splitbind.access.models import Recipient, Role
from splitbind.access.selectors import scope_jobs
from splitbind.audit.models import AuditEvent, AuditOutcome
from splitbind.audit.services import record_event
from splitbind.documents.models import Document, Issuance, Verification
from splitbind.integrations.storage.base import UploadRejected
from splitbind.jobs.models import Job, JobKind, JobStatus
from splitbind.jobs.state import transition_job
from splitbind.outbox.services import create_job_event
from splitbind.uploads.models import PromotionStatus, UploadPurpose, UploadRequest
from splitbind.uploads.services import get_storage


def job_deadline(now):
    from django.conf import settings

    return now + timedelta(seconds=settings.JOB_TIMEOUT_SECONDS)


class WorkflowNotFound(LookupError):
    pass


class JobConflict(ValueError):
    pass


def promoted_input_key(kind: str, organization_id, upload_id) -> str:
    if kind not in JobKind.values:
        raise ValueError("job kind is invalid")
    return f"inputs/{kind}/{organization_id}/{upload_id}.bin"


def _authorize_create(actor, kind: str) -> None:
    allowed = actor.role == Role.ADMINISTRATOR or (
        kind == JobKind.ISSUANCE and actor.role == Role.ISSUER
    ) or (kind == JobKind.VERIFICATION and actor.role == Role.VERIFIER)
    if not allowed:
        raise PermissionDenied("WORKFLOW_FORBIDDEN")


def _purpose(kind: str) -> str:
    return UploadPurpose.ISSUANCE if kind == JobKind.ISSUANCE else UploadPurpose.VERIFICATION


@transaction.atomic
def reserve_promotion(actor, upload_id, kind: str) -> UploadRequest:
    _authorize_create(actor, kind)
    try:
        upload = UploadRequest.objects.select_for_update().get(
            id=upload_id,
            organization_id=actor.organization_id,
            requested_by_id=actor.id,
        )
    except (UploadRequest.DoesNotExist, ValidationError, ValueError) as error:
        raise WorkflowNotFound("WORKFLOW_NOT_FOUND") from error
    if upload.purpose != _purpose(kind):
        raise UploadRejected("UPLOAD_WRONG_PURPOSE")
    if upload.finalized_at is None:
        raise UploadRejected("UPLOAD_NOT_FINALIZED")
    if timezone.now() >= upload.expires_at:
        raise UploadRejected("UPLOAD_EXPIRED")
    if upload.expected_sha256 is None or upload.size_bytes is None:
        raise UploadRejected("UPLOAD_LEGACY_METADATA")
    if upload.promotion_status != PromotionStatus.NONE or upload.promotion_target_key is not None:
        raise JobConflict("PROMOTION_ALREADY_RESERVED")
    target = promoted_input_key(kind, actor.organization_id, upload.id)
    upload.save_promotion(status=PromotionStatus.COPYING, target_key=target, safe_error_code=None)
    return upload


def _mark_failed(upload_id, target_key: str, safe_code: str) -> None:
    with transaction.atomic():
        locked = UploadRequest.objects.select_for_update().get(pk=upload_id)
        if locked.promotion_status == PromotionStatus.COPYING and locked.promotion_target_key == target_key:
            locked.save_promotion(
                status=PromotionStatus.FAILED,
                target_key=target_key,
                safe_error_code=safe_code,
            )


def _verify_copy_observation(copied, upload) -> None:
    if (
        copied is None
        or copied.key != upload.promotion_target_key
        or copied.size_bytes != upload.size_bytes
        or copied.client_sha256_metadata != upload.expected_sha256
    ):
        raise UploadRejected("STORAGE_COPY_MISMATCH")


def _lock_unchanged_reservation(upload, actor, kind):
    locked = UploadRequest.objects.select_for_update().get(pk=upload.id)
    unchanged = (
        locked.promotion_status == PromotionStatus.COPYING
        and locked.promotion_target_key == upload.promotion_target_key
        and locked.organization_id == actor.organization_id
        and locked.requested_by_id == actor.id
        and locked.purpose == _purpose(kind)
        and locked.expected_sha256 == upload.expected_sha256
        and locked.size_bytes == upload.size_bytes
        and locked.finalized_at == upload.finalized_at
    )
    if not unchanged:
        raise JobConflict("PROMOTION_STATE")
    return locked


def _copy_then_finalize(actor, upload, kind: str, correlation_id, create_domain):
    storage = get_storage()
    target = upload.promotion_target_key
    try:
        copied = storage.copy_verified(
            source=upload.object_key,
            destination=target,
            sha256=upload.expected_sha256,
        )
        _verify_copy_observation(copied, upload)
    except Exception:
        try:
            _mark_failed(upload.id, target, "PROMOTION_COPY_FAILED")
        except Exception:
            pass
        raise

    try:
        with transaction.atomic():
            locked = _lock_unchanged_reservation(upload, actor, kind)
            domain = create_domain(locked)
            job = Job.objects.create(
                organization_id=actor.organization_id,
                kind=kind,
                status=JobStatus.CREATED,
                attempt=0,
                issuance=domain if kind == JobKind.ISSUANCE else None,
                verification=domain if kind == JobKind.VERIFICATION else None,
                deadline_at=job_deadline(timezone.now()),
                correlation_id=correlation_id,
            )
            create_job_event(
                job=job,
                input_object_key=target,
                input_sha256=locked.expected_sha256,
            )
            record_event(
                actor,
                f"{kind}.created",
                domain,
                AuditOutcome.SUCCEEDED,
                correlation_id,
                {"status": job.status, "attempt": job.attempt},
            )
            locked.save_promotion(
                status=PromotionStatus.ATTACHED,
                target_key=target,
                safe_error_code=None,
            )
    except Exception:
        try:
            _mark_failed(upload.id, target, "PROMOTION_FINALIZE_FAILED")
        except Exception:
            pass
        raise

    try:
        storage.delete(key=upload.object_key)
    except Exception:
        record_event(
            actor,
            "object.cleanup_deferred_to_lifecycle",
            domain,
            AuditOutcome.FAILED,
            correlation_id,
            {"safe_error_code": "ORPHAN_CLEANUP_DEFERRED", "status": job.status},
        )
    else:
        with transaction.atomic():
            locked_upload = UploadRequest.objects.select_for_update().get(pk=upload.pk)
            if locked_upload.orphan_deleted_at is None:
                locked_upload.orphan_deleted_at = timezone.now()
                locked_upload.save(update_fields=["orphan_deleted_at"])
                record_event(
                    actor,
                    "object.orphan.deleted",
                    locked_upload,
                    AuditOutcome.SUCCEEDED,
                    correlation_id,
                    {"status": "deleted"},
                )
    return domain, job


def _record_denial(actor, action, correlation_id, code):
    record_event(
        actor, action, actor, AuditOutcome.DENIED, correlation_id,
        {"safe_error_code": str(code)},
    )


def create_issuance(actor, recipient_id, upload_id, correlation_id):
    try:
        return _create_issuance(actor, recipient_id, upload_id, correlation_id)
    except (WorkflowNotFound, JobConflict, UploadRejected, PermissionDenied) as error:
        _record_denial(actor, "issuance.create_denied", correlation_id, error)
        raise


def _create_issuance(actor, recipient_id, upload_id, correlation_id):
    _authorize_create(actor, JobKind.ISSUANCE)
    try:
        recipient = Recipient.objects.get(id=recipient_id, organization_id=actor.organization_id)
    except (Recipient.DoesNotExist, ValidationError, ValueError) as error:
        raise WorkflowNotFound("WORKFLOW_NOT_FOUND") from error
    upload = reserve_promotion(actor, upload_id, JobKind.ISSUANCE)

    def create_domain(locked):
        document = Document.objects.create(
            organization_id=actor.organization_id,
            created_by=actor,
            upload_request=locked,
            source_object_key=locked.promotion_target_key,
            expected_source_sha256=locked.expected_sha256,
            page_count=None,
        )
        return Issuance.objects.create(
            organization_id=actor.organization_id,
            document=document,
            recipient=recipient,
            created_by=actor,
        )

    return _copy_then_finalize(
        actor, upload, JobKind.ISSUANCE, correlation_id, create_domain,
    )


def create_verification(actor, upload_id, correlation_id):
    try:
        return _create_verification(actor, upload_id, correlation_id)
    except (WorkflowNotFound, JobConflict, UploadRejected, PermissionDenied) as error:
        _record_denial(actor, "verification.create_denied", correlation_id, error)
        raise


def _create_verification(actor, upload_id, correlation_id):
    _authorize_create(actor, JobKind.VERIFICATION)
    upload = reserve_promotion(actor, upload_id, JobKind.VERIFICATION)

    def create_domain(locked):
        return Verification.objects.create(
            organization_id=actor.organization_id,
            upload_request=locked,
            requested_by=actor,
        )

    return _copy_then_finalize(
        actor, upload, JobKind.VERIFICATION, correlation_id, create_domain,
    )


def request_cancel(actor, job_id, correlation_id):
    try:
        return _request_cancel(actor, job_id, correlation_id)
    except (WorkflowNotFound, JobConflict, PermissionDenied) as error:
        _record_denial(actor, "job.cancel_denied", correlation_id, error)
        raise


def _is_exact_cancel_replay(job, actor, correlation_id) -> bool:
    return AuditEvent.objects.filter(
        organization_id=actor.organization_id,
        actor_id=actor.id,
        action="job.cancel_requested",
        target_type=job._meta.label_lower,
        target_id=str(job.id),
        correlation_id=correlation_id,
        outcome=AuditOutcome.SUCCEEDED,
    ).exists()


@transaction.atomic
def _request_cancel(actor, job_id, correlation_id):
    if actor.role == Role.AUDITOR:
        raise PermissionDenied("WORKFLOW_FORBIDDEN")
    try:
        job = scope_jobs(actor, Job.objects.select_for_update()).get(pk=job_id)
    except (ObjectDoesNotExist, ValidationError, ValueError) as error:
        raise WorkflowNotFound("WORKFLOW_NOT_FOUND") from error
    if job.cancel_requested_at is not None or job.status == JobStatus.CANCELLED:
        if _is_exact_cancel_replay(job, actor, correlation_id):
            return job
        raise JobConflict("JOB_CANCEL_ALREADY_REQUESTED")
    if job.status in {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.DEAD_LETTERED}:
        raise JobConflict("JOB_TERMINAL")
    job.cancel_requested_at = timezone.now()
    if job.status in {JobStatus.CREATED, JobStatus.QUEUED, JobStatus.RETRYABLE_FAILED}:
        transition_job(job, JobStatus.CANCELLED)
    job.save(update_fields=["cancel_requested_at", "status", "updated_at"])
    record_event(
        actor, "job.cancel_requested", job, AuditOutcome.SUCCEEDED, correlation_id,
        {"status": job.status, "attempt": job.attempt},
    )
    return job
