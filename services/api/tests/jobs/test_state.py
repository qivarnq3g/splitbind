import pytest

from splitbind.jobs.models import JobStatus
from splitbind.jobs.state import InvalidJobTransition, transition_job


class MutableJob:
    def __init__(self, status, attempt=0):
        self.status = status
        self.attempt = attempt


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (JobStatus.CREATED, JobStatus.QUEUED),
        (JobStatus.CREATED, JobStatus.CANCELLED),
        (JobStatus.QUEUED, JobStatus.PROCESSING),
        (JobStatus.PROCESSING, JobStatus.SUCCEEDED),
        (JobStatus.PROCESSING, JobStatus.RETRYABLE_FAILED),
        (JobStatus.PROCESSING, JobStatus.CANCELLED),
        (JobStatus.RETRYABLE_FAILED, JobStatus.QUEUED),
        (JobStatus.RETRYABLE_FAILED, JobStatus.DEAD_LETTERED),
    ],
)
def test_transition_table_accepts_declared_edges(source, target):
    job = MutableJob(source)
    transition_job(job, target)
    assert job.status == target


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (JobStatus.CREATED, JobStatus.PROCESSING),
        (JobStatus.SUCCEEDED, JobStatus.FAILED),
        (JobStatus.CANCELLED, JobStatus.QUEUED),
    ],
)
def test_transition_table_rejects_undeclared_or_terminal_edges(source, target):
    with pytest.raises(InvalidJobTransition, match="JOB_TRANSITION"):
        transition_job(MutableJob(source), target)


def test_retry_transition_rejects_attempt_above_bound():
    with pytest.raises(InvalidJobTransition, match="JOB_ATTEMPT"):
        transition_job(MutableJob(JobStatus.RETRYABLE_FAILED, attempt=2), JobStatus.QUEUED)


@pytest.mark.parametrize("attempt", [-1, 3])
def test_transition_rejects_any_job_outside_attempt_bounds(attempt):
    with pytest.raises(InvalidJobTransition, match="JOB_ATTEMPT"):
        transition_job(MutableJob(JobStatus.CREATED, attempt=attempt), JobStatus.FAILED)
