from datetime import timedelta

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from django.utils import timezone

from config.limits import SAFETY_CEILINGS, load_runtime_limits, parse_positive_decimal
from splitbind.jobs.services import job_deadline
from splitbind.integrations.storage.base import UploadRejected
from splitbind.uploads.services import create_upload


@pytest.mark.parametrize("value", ["", " 1", "1 ", "+1", "-1", "0", "1.0", "true", "999999999999999999999999"])
def test_limit_parser_rejects_noncanonical_or_unbounded_values(value):
    with pytest.raises(ImproperlyConfigured):
        parse_positive_decimal("MAX_PDF_BYTES", value)


def test_production_requires_every_limit_and_rejects_above_ceiling():
    complete = {name: str(value) for name, value in SAFETY_CEILINGS.items()}
    missing = dict(complete)
    missing.pop("MAX_PDF_BYTES")
    with pytest.raises(ImproperlyConfigured, match="MAX_PDF_BYTES"):
        load_runtime_limits("production", missing)
    unsafe = dict(complete, MAX_PDF_BYTES=str(10 * 1024 * 1024 + 1))
    with pytest.raises(ImproperlyConfigured, match="MAX_PDF_BYTES"):
        load_runtime_limits("production", unsafe)


def test_reconciliation_lease_is_positive_and_bounded():
    values = {name: str(value) for name, value in SAFETY_CEILINGS.items()}
    values["RETENTION_RECONCILIATION_LEASE_SECONDS"] = "0"
    with pytest.raises(
        ImproperlyConfigured,
        match="RETENTION_RECONCILIATION_LEASE_SECONDS",
    ):
        load_runtime_limits("production", values)

    values["RETENTION_RECONCILIATION_LEASE_SECONDS"] = "601"
    with pytest.raises(ImproperlyConfigured, match="safety ceiling"):
        load_runtime_limits("production", values)


def test_nonproduction_reconciliation_lease_defaults_to_five_minutes():
    assert load_runtime_limits("test", {})[
        "RETENTION_RECONCILIATION_LEASE_SECONDS"
    ] == 300


def test_lower_runtime_job_timeout_reduces_deadline():
    now = timezone.now()
    with override_settings(JOB_TIMEOUT_SECONDS=30):
        assert job_deadline(now) == now + timedelta(seconds=30)


@pytest.mark.django_db
def test_lower_runtime_upload_limit_reduces_accepted_work():
    from splitbind.access.models import Organization, Role, User

    org = Organization.objects.create(name="Lower Limit", slug="lower-limit")
    actor = User.objects.create_user(username="lower", password="test", organization=org, role=Role.ISSUER)
    with override_settings(MAX_PDF_BYTES=1):
        with pytest.raises(UploadRejected, match="UPLOAD_SIZE"):
            create_upload(
                actor,
                kind="issuance_input",
                filename="ignored.pdf",
                content_type="application/pdf",
                size_bytes=2,
                sha256="a" * 64,
            )
