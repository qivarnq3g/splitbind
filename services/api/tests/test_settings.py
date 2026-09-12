import importlib
import sys

import pytest


def load_production_settings(monkeypatch, database_url, **environment):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "fixed-synthetic-test-secret")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.delenv("NEON_DATABASE_HOST", raising=False)
    monkeypatch.delenv("SPLITBIND_DATABASE_HOST", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    defaults = {
        "MAX_PDF_BYTES": str(100 * 1024 * 1024),
        "MAX_PDF_PAGES": "50",
        "MAX_IMAGE_PIXELS": "40000000",
        "MAX_DOCUMENT_RASTER_PIXELS": "120000000",
        "JOB_TIMEOUT_SECONDS": "600",
        "WORKER_CONCURRENCY": "1",
        "RETENTION_RECONCILIATION_LEASE_SECONDS": "300",
    }
    for name, value in defaults.items():
        monkeypatch.setenv(name, value)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    sys.modules.pop("config.settings", None)
    return importlib.import_module("config.settings")


def test_production_settings_require_tls_and_preserve_allowed_connection_options(
    monkeypatch,
):
    settings = load_production_settings(
        monkeypatch,
        "postgresql://synthetic%40user:synthetic%3Apassword@Db.Example.test:6543/splitbind?sslmode=verify-full&channel_binding=require",
        NEON_DATABASE_HOST="db.example.test",
    )

    database = settings.DATABASES["default"]
    assert database["HOST"] == "db.example.test"
    assert database["PORT"] == "6543"
    assert database["USER"] == "synthetic@user"
    assert database["PASSWORD"] == "synthetic:password"
    assert database["OPTIONS"] == {"sslmode": "verify-full", "channel_binding": "require"}


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql://user:password@db.example.test/splitbind",
        "postgresql://user:password@db.example.test/splitbind?sslmode=disable",
        "postgresql://user:password@db.example.test/splitbind?sslmode=require&sslmode=verify-full",
        "postgresql://user:password@db.example.test/splitbind?sslmode=require&application_name=splitbind",
        "postgresql://user:password@db.example.test:0/splitbind?sslmode=require",
        "postgresql://user:password@db.example.test:invalid/splitbind?sslmode=require",
        "postgresql://user:password@db.example.test:65536/splitbind?sslmode=require",
        "postgresql://user:password@db.example.test/splitbind?sslmode=require#fragment",
    ],
)
def test_production_settings_reject_unsafe_or_ambiguous_database_urls(
    monkeypatch, database_url
):
    with pytest.raises(RuntimeError):
        load_production_settings(monkeypatch, database_url)


def test_production_settings_reject_host_mismatch_and_legacy_redirect(monkeypatch):
    url = "postgresql://user:password@db.example.test/splitbind?sslmode=require"

    with pytest.raises(RuntimeError, match="NEON_DATABASE_HOST"):
        load_production_settings(
            monkeypatch,
            url,
            NEON_DATABASE_HOST="other.example.test",
        )
    with pytest.raises(RuntimeError, match="NEON_DATABASE_HOST"):
        load_production_settings(
            monkeypatch,
            url,
            NEON_DATABASE_HOST="db.example.test:invalid",
        )
    with pytest.raises(RuntimeError, match="SPLITBIND_DATABASE_HOST"):
        load_production_settings(
            monkeypatch,
            url,
            SPLITBIND_DATABASE_HOST="other.example.test",
        )


@pytest.mark.parametrize("port", [1, 65535])
def test_production_settings_accept_database_port_boundaries(monkeypatch, port):
    settings = load_production_settings(
        monkeypatch,
        f"postgresql://user:password@db.example.test:{port}/splitbind?sslmode=require",
    )

    assert settings.DATABASES["default"]["PORT"] == str(port)


def test_production_settings_loads_explicit_reconciliation_lease(monkeypatch):
    settings = load_production_settings(
        monkeypatch,
        "postgresql://user:password@db.example.test/splitbind?sslmode=require",
        RETENTION_RECONCILIATION_LEASE_SECONDS="120",
    )

    assert settings.RETENTION_RECONCILIATION_LEASE_SECONDS == 120
