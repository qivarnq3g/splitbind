import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, override_settings

from splitbind.access.models import Organization, Role


API_ROOT = Path(__file__).resolve().parents[2]


def production_environment(*, demo_mode: str) -> dict[str, str]:
    environment = dict(os.environ)
    environment.pop("NEON_DATABASE_HOST", None)
    environment.pop("SPLITBIND_DATABASE_HOST", None)
    environment.update(
        {
            "DJANGO_SECRET_KEY": "fixed-synthetic-test-secret",
            "DATABASE_URL": "postgresql://user:password@db.example.test/splitbind?sslmode=require",
            "ENVIRONMENT": "production",
            "MAX_PDF_BYTES": str(10 * 1024 * 1024),
            "MAX_PDF_PAGES": "50",
            "MAX_IMAGE_PIXELS": "40000000",
            "JOB_TIMEOUT_SECONDS": "600",
            "WORKER_CONCURRENCY": "1",
            "RETENTION_RECONCILIATION_LEASE_SECONDS": "300",
            "SPLITBIND_DEMO_MODE": demo_mode,
        }
    )
    return environment


def test_test_settings_disable_demo_mode_by_default():
    assert settings.SPLITBIND_DEMO_MODE is False


def test_production_settings_reject_enabled_demo_mode():
    result = subprocess.run(
        [sys.executable, "-c", "import config.settings"],
        cwd=API_ROOT,
        env=production_environment(demo_mode="true"),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "SPLITBIND_DEMO_MODE cannot be enabled in production" in result.stderr


def test_settings_reject_unrecognized_demo_mode_value():
    environment = production_environment(demo_mode="enabled")
    environment["ENVIRONMENT"] = "local"
    result = subprocess.run(
        [sys.executable, "-c", "import config.settings"],
        cwd=API_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "SPLITBIND_DEMO_MODE must be exactly true or false" in result.stderr


@pytest.fixture
def issuer(db):
    organization = Organization.objects.create(name="Demo Organization", slug="demo-org")
    return get_user_model().objects.create_user(
        username="demo-issuer",
        password="correct-horse-battery-staple",
        organization=organization,
        role=Role.ISSUER,
    )


@pytest.mark.django_db
def test_demo_capabilities_require_authentication():
    response = Client().get("/api/v1/demo/capabilities")

    assert response.status_code == 403


@pytest.mark.django_db
@override_settings(SPLITBIND_DEMO_MODE=True)
def test_authenticated_capabilities_report_fixed_demo_contract(issuer):
    client = Client()
    client.force_login(issuer)

    response = client.get("/api/v1/demo/capabilities")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
        "processing_limits": {
            "max_pdf_pages": 5,
            "max_pdf_bytes": 10 * 1024 * 1024,
            "max_image_pixels": 40_000_000,
        },
        "algorithm_label": "experimental_unreleased_fingerprint_v2",
    }
