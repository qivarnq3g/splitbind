import importlib
import sys

import pytest


def load_production_settings(monkeypatch, database_url, **environment):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "fixed-synthetic-test-secret")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.delenv("NEON_DATABASE_HOST", raising=False)
    monkeypatch.delenv("SPLITBIND_DATABASE_HOST", raising=False)
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
        "postgresql://user:password@db.example.test:invalid/splitbind?sslmode=require",
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
