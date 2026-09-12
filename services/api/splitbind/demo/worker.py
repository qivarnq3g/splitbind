import inspect
import json
import time
from dataclasses import dataclass
from datetime import timedelta, timezone as datetime_timezone
from uuid import UUID, uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from jsonschema import Draft202012Validator, FormatChecker

from splitbind.demo import issuance as demo_issuance
from splitbind.demo import verification as demo_verification
from splitbind.demo.models import (
    DemoIssuanceResult,
    DemoOutputState,
    DemoVerificationResult,
    DemoVerificationState,
    _allow_demo_result_write,
)
from splitbind.documents.models import Document, Issuance, Verification
from splitbind.jobs.models import Job, JobKind, JobStatus
from splitbind.jobs.state import transition_job
from splitbind.observability import get_logger, log_swallowed
from splitbind.outbox.messages import SCHEMA_PATH
from splitbind.outbox.models import OutboxEvent
from splitbind.uploads.models import UploadRequest


logger = get_logger("splitbind.demo.worker")


DEADLINE_ERROR_CODE = "DEMO_JOB_DEADLINE_EXCEEDED"
STALE_PROCESSING_AGE = timedelta(minutes=15)
STALE_RECONCILIATION_LIMIT = 25
MAX_STALE_RECONCILIATION_LIMIT = 100
STALE_JOB_ERROR_CODE = "DEMO_STALE_JOB_FAILED"
STALE_RESULT_ERROR_CODE = "DEMO_STALE_RESULT_INVALID"
STALE_CLEANUP_ERROR_CODE = "DEMO_STALE_OUTPUT_CLEANUP_FAILED"


@dataclass(frozen=True, slots=True)
class WorkerCycleResult:
    job_id: UUID
    kind: str
    safe_code: str


@dataclass(frozen=True, slots=True)
class StaleRecoveryResult:
    job_id: UUID
    kind: str
    safe_code: str


def _lock_jobs(queryset):
    if connection.features.has_select_for_update_skip_locked:
        return queryset.select_for_update(skip_locked=True)
    return queryset.select_for_update()


def _lock_job_rows(queryset):
    options = {}
    if connection.features.has_select_for_update_skip_locked:
        options["skip_locked"] = True
    if connection.features.has_select_for_update_of:
        options["of"] = ("self",)
    return queryset.select_for_update(**options)


def claim_next_job(
    *,
    owner_token=None,
    now=None,
    enabled=None,
    deadline_error_code=DEADLINE_ERROR_CODE,
    timeout_seconds=None,
    timeout_error_code=None,
):
    if enabled is None:
        enabled = settings.SPLITBIND_DEMO_MODE
    if not enabled:
        return None

    with transaction.atomic():
        job = _lock_jobs(
            Job.objects.filter(status=JobStatus.QUEUED).order_by("created_at", "id")
        ).first()
        if job is None:
            return None
        if job.cancel_requested_at is not None:
            transition_job(job, JobStatus.CANCELLED)
            job.save(update_fields=["status", "updated_at"])
            return None
        observed_now = now or timezone.now()
        if observed_now >= job.deadline_at:
            transition_job(job, JobStatus.FAILED)
            job.safe_error_code = deadline_error_code
            job.save(update_fields=["status", "safe_error_code", "updated_at"])
            return None
        if (
            timeout_seconds is not None
            and observed_now >= job.created_at + timedelta(seconds=timeout_seconds)
        ):
            transition_job(job, JobStatus.FAILED)
            job.safe_error_code = timeout_error_code
            job.save(update_fields=["status", "safe_error_code", "updated_at"])
            return None
        transition_job(job, JobStatus.PROCESSING)
        job.save(update_fields=["status", "updated_at"])
        owner_token = owner_token or uuid4()
        if job.kind == JobKind.ISSUANCE:
            evidence = DemoIssuanceResult(
                organization_id=job.organization_id,
                job=job,
                issuance_id=job.issuance_id,
                attempt=job.attempt,
                owner_token=owner_token,
                output_object_key=(
                    f"outputs/issuance/{job.organization_id}/{job.issuance_id}.pdf"
                ),
            )
        elif job.kind == JobKind.VERIFICATION:
            evidence = DemoVerificationResult(
                organization_id=job.organization_id,
                job=job,
                verification_id=job.verification_id,
                attempt=job.attempt,
                owner_token=owner_token,
            )
        else:
            raise ValidationError("demo job kind is invalid")
        with _allow_demo_result_write():
            evidence.save()
        job._demo_owner_token = owner_token
        return job


def _rfc3339_z(value) -> str:
    return (
        value.astimezone(datetime_timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _locked_job_input(job: Job) -> tuple[str, str] | None:
    if job.kind == JobKind.ISSUANCE and job.issuance_id is not None:
        issuance = Issuance.objects.select_for_update().filter(pk=job.issuance_id).first()
        if issuance is None or issuance.organization_id != job.organization_id:
            return None
        document = Document.objects.select_for_update().filter(pk=issuance.document_id).first()
        if document is None or document.organization_id != job.organization_id:
            return None
        return document.source_object_key, document.expected_source_sha256
    if job.kind == JobKind.VERIFICATION and job.verification_id is not None:
        verification = (
            Verification.objects.select_for_update().filter(pk=job.verification_id).first()
        )
        if verification is None or verification.organization_id != job.organization_id:
            return None
        upload = (
            UploadRequest.objects.select_for_update()
            .filter(pk=verification.upload_request_id)
            .first()
        )
        if upload is None or upload.organization_id != job.organization_id:
            return None
        return upload.promotion_target_key, upload.expected_sha256
    return None


def _outbox_matches_job(event: OutboxEvent, job: Job, input_binding) -> bool:
    if (
        event.organization_id != job.organization_id
        or event.job_id != job.id
        or event.attempt != job.attempt
        or event.published_at is not None
        or input_binding is None
    ):
        return False
    input_object_key, input_sha256 = input_binding
    expected = {
        "schema_version": 1,
        "message_type": f"{job.kind}.requested",
        "message_id": str(event.message_id),
        "job_id": str(job.id),
        "attempt": job.attempt,
        "issuance_id": str(job.issuance_id) if job.issuance_id else None,
        "verification_id": str(job.verification_id) if job.verification_id else None,
        "input_object_key": input_object_key,
        "input_sha256": input_sha256,
        "deadline_at": _rfc3339_z(job.deadline_at),
        "correlation_id": str(job.correlation_id),
    }
    if event.topic != expected["message_type"] or event.payload != expected:
        return False
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return not any(
        Draft202012Validator(
            schema,
            format_checker=FormatChecker(),
        ).iter_errors(event.payload)
    )


def stage_next_created_job(*, enabled=None):
    if enabled is None:
        enabled = settings.SPLITBIND_DEMO_MODE
    if not enabled:
        return None

    with transaction.atomic():
        job = _lock_jobs(
            Job.objects.filter(status=JobStatus.CREATED).order_by("created_at", "id")
        ).first()
        if job is None:
            return None
        events = list(
            OutboxEvent.objects.select_for_update()
            .filter(job_id=job.id)
            .order_by("id")[:2]
        )
        if len(events) != 1 or not _outbox_matches_job(
            events[0],
            job,
            _locked_job_input(job),
        ):
            return None
        transition_job(job, JobStatus.QUEUED)
        job.save(update_fields=["status", "updated_at"])
        return job


def _issuance_claim_for_recovery(job: Job, evidence: DemoIssuanceResult):
    if (
        evidence.organization_id != job.organization_id
        or evidence.job_id != job.id
        or evidence.issuance_id != job.issuance_id
        or evidence.attempt != job.attempt
    ):
        return None
    try:
        issuance, document = demo_issuance._locked_issuance_document(job)
        claim = demo_issuance._ProcessingClaim(
            job_id=job.id,
            organization_id=job.organization_id,
            issuance_id=issuance.id,
            document_id=document.id,
            attempt=job.attempt,
            source_object_key=document.source_object_key,
            expected_source_sha256=document.expected_source_sha256,
            output_object_key=evidence.output_object_key,
            owner_token=evidence.owner_token,
        )
        demo_issuance._validate_claim_binding(claim, job, issuance, document)
        evidence.full_clean()
    except (DemoIssuanceResult.DoesNotExist, demo_issuance.DemoIssuanceError, ValidationError):
        return None
    return claim, issuance, document


def _verification_claim_for_recovery(job: Job, result: DemoVerificationResult):
    if (
        result.organization_id != job.organization_id
        or result.job_id != job.id
        or result.verification_id != job.verification_id
        or result.attempt != job.attempt
    ):
        return None
    try:
        verification, upload = demo_verification._locked_verification_upload(job)
        claim = demo_verification._ProcessingClaim(
            job_id=job.id,
            organization_id=job.organization_id,
            verification_id=verification.id,
            upload_id=upload.id,
            attempt=job.attempt,
            input_object_key=upload.promotion_target_key,
            expected_input_sha256=upload.expected_sha256,
            owner_token=result.owner_token,
        )
        demo_verification._validate_claim_binding(
            claim,
            job,
            verification,
            upload,
        )
        result.full_clean()
    except (
        DemoVerificationResult.DoesNotExist,
        demo_verification.DemoVerificationError,
        ValidationError,
    ):
        return None
    return claim, verification, upload


def _terminalize_locked_job(job: Job, status: str, safe_code: str | None) -> None:
    transition_job(job, status)
    job.safe_error_code = safe_code
    job.save(update_fields=["status", "safe_error_code", "updated_at"])


@transaction.atomic
def _prepare_stale_recovery(job_id: UUID, stale_before):
    job = Job.objects.select_for_update().filter(pk=job_id).first()
    if job is not None and job.kind == JobKind.ISSUANCE and job.status == JobStatus.FAILED:
        evidence = (
            DemoIssuanceResult.objects.select_for_update().filter(job_id=job.id).first()
        )
        if (
            evidence is not None
            and evidence.output_state == DemoOutputState.CLEANUP_REQUIRED
            and evidence.safe_error_code
            == demo_issuance.DEMO_STALE_RECOVERY_FENCE_CODE
        ):
            prepared = _issuance_claim_for_recovery(job, evidence)
            if prepared is not None:
                claim, _issuance, _document = prepared
                return "tombstone", claim, evidence.cleanup_failures
    if (
        job is None
        or job.status != JobStatus.PROCESSING
        or job.updated_at >= stale_before
    ):
        return None

    if job.kind == JobKind.ISSUANCE:
        evidence = (
            DemoIssuanceResult.objects.select_for_update().filter(job_id=job.id).first()
        )
        if evidence is None:
            return None
        prepared = _issuance_claim_for_recovery(job, evidence)
        if prepared is None:
            return None
        claim, issuance, document = prepared
        if evidence.output_state == DemoOutputState.COMMITTED:
            try:
                demo_issuance._load_replay_result(job, issuance, document)
            except (demo_issuance.DemoIssuanceError, ValidationError):
                _terminalize_locked_job(
                    job,
                    JobStatus.FAILED,
                    STALE_RESULT_ERROR_CODE,
                )
                return StaleRecoveryResult(job.id, job.kind, STALE_RESULT_ERROR_CODE)
            _terminalize_locked_job(job, JobStatus.SUCCEEDED, None)
            return StaleRecoveryResult(job.id, job.kind, "OK")
        if evidence.output_state in {
            DemoOutputState.UPLOADING,
            DemoOutputState.CLEANUP_REQUIRED,
        }:
            recovery_claim, prior_cleanup_failures = (
                demo_issuance._claim_stale_output_recovery(
                    claim,
                    recovery_token=uuid4(),
                )
            )
            return "cleanup", recovery_claim, prior_cleanup_failures
        if evidence.output_state in {
            DemoOutputState.RESERVED,
            DemoOutputState.CLEANED,
        }:
            demo_issuance._record_failed_job(
                claim,
                demo_issuance.DemoIssuanceError(STALE_JOB_ERROR_CODE),
            )
            return StaleRecoveryResult(job.id, job.kind, STALE_JOB_ERROR_CODE)
        return None

    if job.kind == JobKind.VERIFICATION:
        result = (
            DemoVerificationResult.objects.select_for_update()
            .filter(job_id=job.id)
            .first()
        )
        if result is None:
            return None
        prepared = _verification_claim_for_recovery(job, result)
        if prepared is None:
            return None
        claim, verification, upload = prepared
        if result.result_state == DemoVerificationState.COMMITTED:
            try:
                demo_verification._load_replay_result(job, verification, upload)
            except (demo_verification.DemoVerificationError, ValidationError):
                _terminalize_locked_job(
                    job,
                    JobStatus.FAILED,
                    STALE_RESULT_ERROR_CODE,
                )
                return StaleRecoveryResult(job.id, job.kind, STALE_RESULT_ERROR_CODE)
            _terminalize_locked_job(job, JobStatus.SUCCEEDED, None)
            return StaleRecoveryResult(job.id, job.kind, "OK")
        if result.result_state == DemoVerificationState.RESERVED:
            demo_verification._record_failed_job(
                claim,
                demo_verification.DemoVerificationError(STALE_JOB_ERROR_CODE),
                started=time.monotonic(),
            )
            return StaleRecoveryResult(job.id, job.kind, STALE_JOB_ERROR_CODE)
    return None


def _recover_stale_job(*, job_id: UUID, stale_before, storage):
    prepared = _prepare_stale_recovery(job_id, stale_before)
    if not isinstance(prepared, tuple):
        return prepared
    action, claim, prior_cleanup_failures = prepared
    if action == "tombstone":
        try:
            storage.delete(key=claim.output_object_key)
        except Exception as error:
            log_swallowed(
                logger,
                error,
                action="stale_cleanup",
                job=claim.job_id,
                code=STALE_CLEANUP_ERROR_CODE,
            )
            return StaleRecoveryResult(
                claim.job_id,
                JobKind.ISSUANCE,
                STALE_CLEANUP_ERROR_CODE,
            )
        return StaleRecoveryResult(
            claim.job_id,
            JobKind.ISSUANCE,
            STALE_JOB_ERROR_CODE,
        )
    if action != "cleanup":
        return None
    demo_issuance._authorize_stale_output_delete(
        claim,
        cleanup_failures=prior_cleanup_failures,
    )
    try:
        storage.delete(key=claim.output_object_key)
    except Exception as error:
        log_swallowed(
            logger,
            error,
            action="stale_cleanup",
            job=claim.job_id,
            code=STALE_CLEANUP_ERROR_CODE,
        )
        demo_issuance._record_stale_output_delete_failure(
            claim,
            prior_cleanup_failures=prior_cleanup_failures,
            safe_error_code=STALE_CLEANUP_ERROR_CODE,
        )
        return StaleRecoveryResult(
            claim.job_id,
            JobKind.ISSUANCE,
            STALE_CLEANUP_ERROR_CODE,
        )
    demo_issuance._acknowledge_stale_output_delete(
        claim,
        cleanup_failures=prior_cleanup_failures,
        safe_error_code=STALE_JOB_ERROR_CODE,
    )
    return StaleRecoveryResult(
        claim.job_id,
        JobKind.ISSUANCE,
        STALE_JOB_ERROR_CODE,
    )


def reconcile_stale_jobs(
    *,
    storage,
    limit: int = STALE_RECONCILIATION_LIMIT,
    now=None,
    enabled=None,
    stale_age=STALE_PROCESSING_AGE,
) -> tuple[StaleRecoveryResult, ...]:
    if enabled is None:
        enabled = settings.SPLITBIND_DEMO_MODE
    if not enabled:
        return ()
    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or not 1 <= limit <= MAX_STALE_RECONCILIATION_LIMIT
    ):
        raise ValueError("stale reconciliation limit is out of bounds")
    observed_now = now or timezone.now()
    stale_before = observed_now - stale_age
    issuance_owner = DemoIssuanceResult.objects.filter(job_id=OuterRef("pk"))
    verification_owner = DemoVerificationResult.objects.filter(job_id=OuterRef("pk"))
    issuance_tombstone = DemoIssuanceResult.objects.filter(
        job_id=OuterRef("pk"),
        output_state=DemoOutputState.CLEANUP_REQUIRED,
        safe_error_code=demo_issuance.DEMO_STALE_RECOVERY_FENCE_CODE,
    )
    with transaction.atomic():
        candidate_ids = list(
            _lock_job_rows(
                Job.objects.annotate(
                    has_demo_issuance_owner=Exists(issuance_owner),
                    has_demo_verification_owner=Exists(verification_owner),
                    has_demo_issuance_tombstone=Exists(issuance_tombstone),
                )
                .filter(
                    Q(
                        Q(has_demo_issuance_owner=True)
                        | Q(has_demo_verification_owner=True),
                        status=JobStatus.PROCESSING,
                        updated_at__lt=stale_before,
                    )
                    | Q(
                        has_demo_issuance_tombstone=True,
                        status=JobStatus.FAILED,
                    )
                )
                .order_by("updated_at", "id")
            ).values_list("id", flat=True)[:limit]
        )
    outcomes = []
    for job_id in candidate_ids:
        outcome = _recover_stale_job(
            job_id=job_id,
            stale_before=stale_before,
            storage=storage,
        )
        if outcome is not None:
            outcomes.append(outcome)
    return tuple(outcomes)


def run_worker_cycle(*, storage) -> WorkerCycleResult | None:
    stage_next_created_job()
    job = claim_next_job()
    if job is None:
        return None
    try:
        if job.kind == JobKind.ISSUANCE:
            processor = demo_issuance.process_issuance_job
            kwargs = {"job_id": job.id, "storage": storage}
            if "owner_token" in inspect.signature(processor).parameters:
                kwargs["owner_token"] = job._demo_owner_token
            processor(**kwargs)
        elif job.kind == JobKind.VERIFICATION:
            processor = demo_verification.process_verification_job
            kwargs = {"job_id": job.id, "storage": storage}
            if "owner_token" in inspect.signature(processor).parameters:
                kwargs["owner_token"] = job._demo_owner_token
            processor(**kwargs)
        else:
            return WorkerCycleResult(
                job_id=job.id,
                kind=job.kind,
                safe_code="DEMO_JOB_KIND_INVALID",
            )
    except Exception as error:
        log_swallowed(
            logger,
            error,
            action="cycle",
            job=job.id,
            kind=job.kind,
            code="DEMO_JOB_PROCESSING_FAILED",
        )
        return WorkerCycleResult(
            job_id=job.id,
            kind=job.kind,
            safe_code="DEMO_JOB_PROCESSING_FAILED",
        )
    return WorkerCycleResult(job_id=job.id, kind=job.kind, safe_code="OK")
