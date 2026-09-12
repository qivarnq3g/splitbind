from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import connection, transaction

from splitbind.demo import issuance as demo_issuance
from splitbind.demo import verification as demo_verification
from splitbind.demo.models import DemoIssuanceResult, DemoVerificationResult
from splitbind.demo.worker import (
    WorkerCycleResult,
    claim_next_job,
    reconcile_stale_jobs,
    stage_next_created_job,
)
from splitbind.jobs.models import Job, JobKind, JobStatus
from splitbind.observability import get_logger, log_swallowed
from splitbind.jobs.state import transition_job
from splitbind.release.manifest import load_manifest_signing_key
from splitbind.release.mode import integrity_release_enabled


logger = get_logger("splitbind.release.worker")

INTEGRITY_DEADLINE_ERROR_CODE = "INTEGRITY_JOB_DEADLINE_EXCEEDED"
INTEGRITY_TIMEOUT_ERROR_CODE = "INTEGRITY_JOB_TIMEOUT_EXCEEDED"
INTEGRITY_ATTEMPTS_EXHAUSTED = "INTEGRITY_JOB_ATTEMPTS_EXHAUSTED"
INTEGRITY_RESULT_ALREADY_OWNED = "INTEGRITY_JOB_RESULT_ALREADY_OWNED"
MAX_JOB_ATTEMPT = 2


def _require_integrity_mode() -> None:
    if not integrity_release_enabled(getattr(settings, "SPLITBIND_RELEASE_MODE", None)):
        raise ImproperlyConfigured("INTEGRITY_RELEASE_MODE_REQUIRED")


def _lock_jobs(queryset):
    if connection.features.has_select_for_update_skip_locked:
        return queryset.select_for_update(skip_locked=True)
    return queryset.select_for_update()


def _prepare_one_retry(*, now: datetime) -> None:
    """Move at most one retryable job back to the queue without exceeding attempt 2."""
    with transaction.atomic():
        job = _lock_jobs(
            Job.objects.filter(status=JobStatus.RETRYABLE_FAILED).order_by(
                "updated_at", "id"
            )
        ).first()
        if job is None:
            return
        if job.cancel_requested_at is not None:
            transition_job(job, JobStatus.CANCELLED)
            job.save(update_fields=["status", "updated_at"])
            return
        if now >= job.deadline_at:
            transition_job(job, JobStatus.FAILED)
            job.safe_error_code = INTEGRITY_DEADLINE_ERROR_CODE
            job.save(update_fields=["status", "safe_error_code", "updated_at"])
            return
        result_exists = (
            DemoIssuanceResult.objects.filter(job_id=job.id).exists()
            if job.kind == JobKind.ISSUANCE
            else DemoVerificationResult.objects.filter(job_id=job.id).exists()
        )
        if result_exists:
            transition_job(job, JobStatus.DEAD_LETTERED)
            job.safe_error_code = INTEGRITY_RESULT_ALREADY_OWNED
            job.save(update_fields=["status", "safe_error_code", "updated_at"])
            return
        if job.attempt >= MAX_JOB_ATTEMPT:
            transition_job(job, JobStatus.DEAD_LETTERED)
            job.safe_error_code = INTEGRITY_ATTEMPTS_EXHAUSTED
            job.save(update_fields=["status", "safe_error_code", "updated_at"])
            return
        transition_job(job, JobStatus.QUEUED)
        job.attempt += 1
        job.safe_error_code = None
        job.save(update_fields=["status", "attempt", "safe_error_code", "updated_at"])


def claim_next_integrity_job(owner_token: uuid.UUID, now: datetime):
    _require_integrity_mode()
    if not isinstance(owner_token, uuid.UUID):
        raise ValueError("INTEGRITY_OWNER_TOKEN_INVALID")
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("INTEGRITY_NOW_INVALID")
    _prepare_one_retry(now=now)
    return claim_next_job(
        owner_token=owner_token,
        now=now,
        enabled=True,
        deadline_error_code=INTEGRITY_DEADLINE_ERROR_CODE,
        timeout_seconds=settings.JOB_TIMEOUT_SECONDS,
        timeout_error_code=INTEGRITY_TIMEOUT_ERROR_CODE,
    )


def process_integrity_cycle(storage, now: datetime) -> WorkerCycleResult | None:
    _require_integrity_mode()
    stage_next_created_job(enabled=True)
    job = claim_next_integrity_job(uuid.uuid4(), now)
    if job is None:
        return None
    try:
        if job.kind == JobKind.ISSUANCE:
            demo_issuance.process_issuance_job(
                job_id=job.id,
                storage=storage,
                owner_token=job._demo_owner_token,
            )
        elif job.kind == JobKind.VERIFICATION:
            demo_verification.process_verification_job(
                job_id=job.id,
                storage=storage,
                owner_token=job._demo_owner_token,
            )
        else:
            return WorkerCycleResult(job.id, job.kind, "INTEGRITY_JOB_KIND_INVALID")
    except Exception as error:
        log_swallowed(
            logger,
            error,
            action="cycle",
            job=job.id,
            kind=job.kind,
            code="INTEGRITY_JOB_PROCESSING_FAILED",
        )
        return WorkerCycleResult(job.id, job.kind, "INTEGRITY_JOB_PROCESSING_FAILED")
    return WorkerCycleResult(job.id, job.kind, "OK")


def recover_stale_integrity_jobs(*, storage, now: datetime):
    _require_integrity_mode()
    return reconcile_stale_jobs(
        storage=storage,
        now=now,
        enabled=True,
        stale_age=timedelta(seconds=settings.JOB_TIMEOUT_SECONDS),
    )


def validate_integrity_worker_startup() -> None:
    _require_integrity_mode()
    expected_limits = {
        "MAX_PDF_BYTES": 100 * 1024 * 1024,
        "MAX_PDF_PAGES": 50,
        "MAX_IMAGE_PIXELS": 40_000_000,
        "MAX_DOCUMENT_RASTER_PIXELS": 120_000_000,
        "JOB_TIMEOUT_SECONDS": 600,
        "WORKER_CONCURRENCY": 1,
    }
    if any(getattr(settings, name, None) != value for name, value in expected_limits.items()):
        raise ImproperlyConfigured("INTEGRITY_LIMITS_INVALID")
    if connection.vendor != "postgresql":
        raise ImproperlyConfigured("INTEGRITY_DATABASE_INVALID")
    try:
        connection.ensure_connection()
    except Exception:
        raise ImproperlyConfigured("INTEGRITY_DATABASE_UNAVAILABLE") from None
    key_file = getattr(settings, "SPLITBIND_MANIFEST_SIGNING_KEY_FILE", None)
    passphrase_file = getattr(
        settings,
        "SPLITBIND_MANIFEST_SIGNING_KEY_PASSPHRASE_FILE",
        None,
    )
    if not key_file or not passphrase_file:
        raise ImproperlyConfigured("INTEGRITY_SIGNING_KEY_INVALID")
    try:
        load_manifest_signing_key(key_file, passphrase_file)
    except (OSError, TypeError, ValueError):
        raise ImproperlyConfigured("INTEGRITY_SIGNING_KEY_INVALID") from None
