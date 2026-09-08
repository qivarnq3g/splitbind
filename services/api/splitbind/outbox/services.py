import uuid

from splitbind.outbox.messages import build_job_request
from splitbind.outbox.models import OutboxEvent


def create_job_event(*, job, input_object_key: str, input_sha256: str) -> OutboxEvent:
    payload = build_job_request(
        job=job, input_object_key=input_object_key, input_sha256=input_sha256,
    )
    return OutboxEvent.objects.create(
        organization_id=job.organization_id,
        message_id=uuid.UUID(payload["message_id"]),
        job=job,
        attempt=job.attempt,
        topic=payload["message_type"],
        payload=payload,
    )
