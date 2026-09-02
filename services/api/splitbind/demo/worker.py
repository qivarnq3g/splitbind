from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from splitbind.jobs.models import Job, JobStatus
from splitbind.jobs.state import transition_job


DEADLINE_ERROR_CODE = "DEMO_JOB_DEADLINE_EXCEEDED"


def _lock_jobs(queryset):
    if connection.features.has_select_for_update_skip_locked:
        return queryset.select_for_update(skip_locked=True)
    return queryset.select_for_update()


def claim_next_job():
    if not settings.SPLITBIND_DEMO_MODE:
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
        if timezone.now() >= job.deadline_at:
            transition_job(job, JobStatus.FAILED)
            job.safe_error_code = DEADLINE_ERROR_CODE
            job.save(update_fields=["status", "safe_error_code", "updated_at"])
            return None
        transition_job(job, JobStatus.PROCESSING)
        job.save(update_fields=["status", "updated_at"])
        return job
