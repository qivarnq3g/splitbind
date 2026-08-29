from rest_framework import serializers

from splitbind.validators import SHA256_PATTERN


class UploadIntentSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["issuance_input", "verification_input"])
    filename = serializers.CharField(max_length=255, allow_blank=False, write_only=True)
    content_type = serializers.CharField(max_length=100)
    size_bytes = serializers.IntegerField(min_value=1, max_value=10 * 1024 * 1024)
    sha256 = serializers.RegexField(SHA256_PATTERN)


class UploadCompleteSerializer(serializers.Serializer):
    sha256 = serializers.RegexField(SHA256_PATTERN)


def serialize_upload(record, *, upload_url=None, required_headers=None):
    payload = {
        "id": str(record.id),
        "object_key": record.object_key,
        "sha256": record.sha256,
        "size_bytes": record.size_bytes,
        "expires_at": record.expires_at.isoformat(),
        "finalized_at": record.finalized_at.isoformat() if record.finalized_at else None,
    }
    if upload_url is not None:
        payload["upload_url"] = upload_url
        payload["required_headers"] = required_headers
    return payload
