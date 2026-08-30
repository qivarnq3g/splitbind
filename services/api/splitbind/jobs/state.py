from splitbind.jobs.models import JobStatus


class InvalidJobTransition(ValueError):
    pass


TRANSITIONS = {
    JobStatus.CREATED: {JobStatus.QUEUED, JobStatus.CANCELLED, JobStatus.FAILED},
    JobStatus.QUEUED: {JobStatus.PROCESSING, JobStatus.CANCELLED, JobStatus.FAILED, JobStatus.DEAD_LETTERED},
    JobStatus.PROCESSING: {
        JobStatus.SUCCEEDED,
        JobStatus.FAILED,
        JobStatus.RETRYABLE_FAILED,
        JobStatus.CANCELLED,
    },
    JobStatus.RETRYABLE_FAILED: {JobStatus.QUEUED, JobStatus.FAILED, JobStatus.DEAD_LETTERED, JobStatus.CANCELLED},
    JobStatus.SUCCEEDED: set(),
    JobStatus.FAILED: set(),
    JobStatus.DEAD_LETTERED: set(),
    JobStatus.CANCELLED: set(),
}


def transition_job(job, target: str) -> None:
    if not isinstance(job.attempt, int) or isinstance(job.attempt, bool) or not 0 <= job.attempt <= 2:
        raise InvalidJobTransition("JOB_ATTEMPT")
    if target not in JobStatus.values or target not in TRANSITIONS.get(job.status, set()):
        raise InvalidJobTransition("JOB_TRANSITION")
    if job.status == JobStatus.RETRYABLE_FAILED and target == JobStatus.QUEUED and job.attempt >= 2:
        raise InvalidJobTransition("JOB_ATTEMPT")
    job.status = target
