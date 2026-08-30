from rest_framework import serializers


class CancelJobSerializer(serializers.Serializer):
    correlation_id = serializers.UUIDField()


def serialize_job(job):
    return {
        "id": str(job.id),
        "kind": job.kind,
        "status": job.status,
        "attempt": job.attempt,
        "issuance_id": str(job.issuance_id) if job.issuance_id else None,
        "verification_id": str(job.verification_id) if job.verification_id else None,
        "deadline_at": job.deadline_at.isoformat(),
        "cancel_requested_at": job.cancel_requested_at.isoformat() if job.cancel_requested_at else None,
        "safe_error_code": job.safe_error_code,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }
