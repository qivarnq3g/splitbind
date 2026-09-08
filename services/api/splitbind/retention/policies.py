from datetime import datetime, timedelta, timezone


RETENTION_WINDOWS = {
    "orphan_upload": timedelta(hours=24),
    "issuance_input": timedelta(days=7),
    "issuance_output": timedelta(days=30),
    "verification_input": timedelta(hours=24),
}
INDEFINITE_KINDS = {"manifest_metadata", "audit_event"}


def retention_deadline(kind: str, completed_at: datetime) -> datetime | None:
    if not isinstance(completed_at, datetime) or completed_at.tzinfo is None:
        raise ValueError("retention timestamp must be timezone-aware UTC")
    if completed_at.utcoffset() != timedelta(0):
        raise ValueError("retention timestamp must be timezone-aware UTC")
    if kind in INDEFINITE_KINDS:
        return None
    try:
        return completed_at.astimezone(timezone.utc) + RETENTION_WINDOWS[kind]
    except KeyError as error:
        raise ValueError("unknown retention kind") from error
