from datetime import datetime, timedelta, timezone

import pytest

from splitbind.retention.policies import retention_deadline


NOW = datetime(2026, 8, 30, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("kind", "delta"),
    [
        ("orphan_upload", timedelta(hours=24)),
        ("issuance_input", timedelta(days=7)),
        ("issuance_output", timedelta(days=30)),
        ("verification_input", timedelta(hours=24)),
    ],
)
def test_retention_windows_match_spec(kind, delta):
    assert retention_deadline(kind, NOW) == NOW + delta


def test_retention_requires_aware_utc_and_unknown_kind_fails_closed():
    with pytest.raises(ValueError, match="unknown"):
        retention_deadline("mystery", NOW)
    with pytest.raises(ValueError, match="timezone-aware"):
        retention_deadline("orphan_upload", NOW.replace(tzinfo=None))
