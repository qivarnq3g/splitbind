from collections.abc import Mapping
from urllib.parse import urlparse


SAFE_AUDIT_KEYS = {
    "kind",
    "role",
    "status",
    "safe_error_code",
    "object_size",
    "attempt",
}
MAX_AUDIT_METADATA_VALUE_LENGTH = 256


def _is_full_url(value: str) -> bool:
    parsed = urlparse(value)
    return bool(parsed.netloc and (parsed.scheme or value.startswith("//")))


def redact_metadata(metadata: Mapping[str, object] | None) -> dict[str, str]:
    """Keep only bounded, allow-listed scalar audit metadata.

    Unknown keys are dropped rather than transformed, so case variants of
    sensitive names cannot enter the audit trail. Nested values and complete
    URLs are also dropped because their representation can contain secrets.
    """
    if not isinstance(metadata, Mapping):
        return {}

    safe: dict[str, str] = {}
    for key, value in metadata.items():
        if key not in SAFE_AUDIT_KEYS or isinstance(value, (dict, list, tuple, set)):
            continue
        if not isinstance(value, (str, int, float, bool)) or value is None:
            continue
        normalized = str(value)
        if _is_full_url(normalized):
            continue
        safe[key] = normalized[:MAX_AUDIT_METADATA_VALUE_LENGTH]
    return safe


sanitize_metadata = redact_metadata
