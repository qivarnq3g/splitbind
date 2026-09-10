from rest_framework import serializers


class CancelJobSerializer(serializers.Serializer):
    correlation_id = serializers.UUIDField()


def serialize_job(job):
    data = {
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
        "recipient_email": None,
        "recipient_name": None,
        "verification_status": None,
    }
    if job.issuance_id:
        try:
            recipient = getattr(job.issuance, "recipient", None)
            if recipient:
                data["recipient_email"] = recipient.external_reference
                data["recipient_name"] = recipient.display_name
        except Exception:
            pass
    if job.verification_id:
        try:
            if hasattr(job, "verification") and job.verification:
                data["verification_status"] = job.verification.status
        except Exception:
            pass
    return data
