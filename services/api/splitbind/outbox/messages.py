import json
import uuid
from datetime import timezone as datetime_timezone
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from jsonschema import Draft202012Validator, FormatChecker


SCHEMA_PATH = Path(settings.BASE_DIR).parents[1] / "contracts" / "jsonschema" / "job-request-v1.schema.json"


def _rfc3339_z(value) -> str:
    return value.astimezone(datetime_timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def build_job_request(*, job, input_object_key: str, input_sha256: str) -> dict:
    payload = {
        "schema_version": 1,
        "message_type": f"{job.kind}.requested",
        "message_id": str(uuid.uuid4()),
        "job_id": str(job.id),
        "attempt": job.attempt,
        "issuance_id": str(job.issuance_id) if job.issuance_id else None,
        "verification_id": str(job.verification_id) if job.verification_id else None,
        "input_object_key": input_object_key,
        "input_sha256": input_sha256,
        "deadline_at": _rfc3339_z(job.deadline_at),
        "correlation_id": str(job.correlation_id),
    }
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload),
        key=lambda error: list(error.path),
    )
    if errors:
        raise ValidationError("job request does not satisfy the versioned schema")
    return payload
