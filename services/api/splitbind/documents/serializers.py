import re

from django.conf import settings
from rest_framework import serializers

from splitbind.jobs.models import JobStatus
from splitbind.release.mode import integrity_release_enabled


class IssuanceCreateSerializer(serializers.Serializer):
    recipient_id = serializers.UUIDField(required=False)
    recipient_email = serializers.EmailField(required=False, allow_blank=False, max_length=120)
    recipient_name = serializers.CharField(required=False, allow_blank=True, max_length=200)
    upload_id = serializers.UUIDField()
    correlation_id = serializers.UUIDField()

    def validate(self, attrs):
        has_id = bool(attrs.get("recipient_id"))
        has_email = bool(attrs.get("recipient_email"))
        if has_id and has_email:
            raise serializers.ValidationError(
                "Chỉ được cung cấp mã người nhận (recipient_id) hoặc email người nhận (recipient_email), không được cung cấp cả hai."
            )
        if not has_id and not has_email:
            raise serializers.ValidationError(
                "Cần cung cấp email người nhận (recipient_email) hoặc mã người nhận (recipient_id)."
            )
        if has_email:
            attrs["recipient_email"] = attrs["recipient_email"].strip()
            if attrs.get("recipient_name") is not None:
                attrs["recipient_name"] = attrs["recipient_name"].strip()
        return attrs


class VerificationCreateSerializer(serializers.Serializer):
    upload_id = serializers.UUIDField()
    correlation_id = serializers.UUIDField()


_LIMITATION_ID = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_METRIC_KEYS = {
    "processing_ms", "pages_processed", "peak_rss_bytes", "temp_peak_bytes",
    "cleanup_failures",
}


def _contract_evidence(value):
    if not isinstance(value, dict):
        return {}
    integrity_mode = integrity_release_enabled(
        getattr(settings, "SPLITBIND_RELEASE_MODE", None)
    )
    algorithm_label = value.get("algorithm_label")
    if integrity_mode and algorithm_label == "experimental_unreleased_fingerprint_v2":
        algorithm_label = "integrity_release_v1"
    projected = {
        "algorithm_label": (
            algorithm_label
            if algorithm_label
            in {"experimental_unreleased_fingerprint_v2", "integrity_release_v1"}
            else None
        ),
        "decode_status": (
            value.get("decode_status")
            if value.get("decode_status")
            in {
                "decoded",
                "partial_payload_evidence",
                "payload_not_detected",
                "insufficient_sync_evidence",
                "geometry_rejected",
                "execution_error",
                "cancelled",
            }
            else None
        ),
    }
    for key in ("fingerprint_confidence", "integrity_score"):
        item = value.get(key)
        if item is None and key == "integrity_score" and key in value:
            projected[key] = None
        elif isinstance(item, (int, float)) and not isinstance(item, bool) and 0 <= item <= 1:
            projected[key] = item
    for key in ("valid_vote_count", "analyzed_page_count"):
        item = value.get(key)
        if isinstance(item, int) and not isinstance(item, bool) and item >= 0:
            projected[key] = item
    for key in ("manifest_signature_valid", "exact_file_hash_match"):
        item = value.get(key)
        if (isinstance(item, bool) or item is None) and key in value:
            projected[key] = item
    regions = value.get("suspicious_regions")
    if isinstance(regions, list):
        safe_regions = []
        for region in regions[:500]:
            if not isinstance(region, dict) or set(region) != {"x", "y", "width", "height"}:
                continue
            if all(
                isinstance(region[key], (int, float))
                and not isinstance(region[key], bool)
                and 0 <= region[key] <= 1
                for key in region
            ) and region["width"] > 0 and region["height"] > 0:
                safe_regions.append({key: region[key] for key in ("x", "y", "width", "height")})
        projected["suspicious_regions"] = safe_regions
    limitations = value.get("limitations")
    if integrity_mode:
        projected_limitations = ["evidence.not_proof_of_leak_edit_or_distribution"]
        if projected.get("exact_file_hash_match") is not True:
            projected_limitations.append(
                "fingerprint.transformed_attribution_unavailable"
            )
        projected["limitations"] = projected_limitations
    elif isinstance(limitations, list):
        projected_limitations = [
            item for item in limitations[:100]
            if isinstance(item, str) and _LIMITATION_ID.fullmatch(item)
        ]
        projected["limitations"] = projected_limitations
    return projected


def _contract_metrics(value):
    if not isinstance(value, dict):
        return {}
    return {
        key: value[key]
        for key in _METRIC_KEYS
        if isinstance(value.get(key), int)
        and not isinstance(value[key], bool)
        and 0 <= value[key] <= 2**63 - 1
    }


def issuance_result_evidence(record, job=None):
    from splitbind.demo.capabilities import DEMO_ALGORITHM_LABEL
    from splitbind.demo.models import DemoOutputState

    job = job or record.jobs.order_by("created_at").first()
    evidence = getattr(record, "demo_result", None)
    if (
        job is None
        or evidence is None
        or evidence.output_state != DemoOutputState.COMMITTED
        or evidence.algorithm_label != DEMO_ALGORITHM_LABEL
        or evidence.issuance_id != record.id
        or evidence.organization_id != record.organization_id
        or evidence.job_id != job.id
        or evidence.job.organization_id != record.organization_id
        or evidence.job.status != JobStatus.SUCCEEDED
        or evidence.job.issuance_id != record.id
        or evidence.attempt != evidence.job.attempt
        or not record.output_object_key
        or not record.output_sha256
        or record.output_deleted_at is not None
        or evidence.output_object_key != record.output_object_key
        or evidence.output_sha256 != record.output_sha256
    ):
        return None
    return evidence


def serialize_issuance(record, job=None):
    job = job or record.jobs.order_by("created_at").first()
    evidence = issuance_result_evidence(record, job)
    return {
        "id": str(record.id),
        "job_id": str(job.id) if job else None,
        "status": job.status if job else None,
        "issued_at": record.issued_at.isoformat(),
        "result_available": evidence is not None,
        "algorithm_label": (
            "integrity_release_v1"
            if evidence
            and integrity_release_enabled(getattr(settings, "SPLITBIND_RELEASE_MODE", None))
            else evidence.algorithm_label if evidence else None
        ),
    }


def serialize_verification(record, job=None):
    job = job or record.jobs.order_by("created_at").first()
    return {
        "id": str(record.id),
        "job_id": str(job.id) if job else None,
        "job_status": job.status if job else None,
        "status": record.status,
        "created_at": record.created_at.isoformat(),
        "completed_at": record.completed_at.isoformat() if record.completed_at else None,
        "evidence": _contract_evidence(record.evidence),
        "metrics": _contract_metrics(record.metrics),
    }
