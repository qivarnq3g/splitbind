import re

from rest_framework import serializers


class IssuanceCreateSerializer(serializers.Serializer):
    recipient_id = serializers.UUIDField()
    upload_id = serializers.UUIDField()
    correlation_id = serializers.UUIDField()


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
    projected = {}
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
    if isinstance(limitations, list):
        projected["limitations"] = [
            item for item in limitations[:100]
            if isinstance(item, str) and _LIMITATION_ID.fullmatch(item)
        ]
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


def serialize_issuance(record, job=None):
    job = job or record.jobs.order_by("created_at").first()
    return {
        "id": str(record.id),
        "job_id": str(job.id) if job else None,
        "status": job.status if job else None,
        "issued_at": record.issued_at.isoformat(),
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
