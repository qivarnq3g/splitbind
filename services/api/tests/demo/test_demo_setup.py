import io
import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.core.management import call_command
from django.test import override_settings

from splitbind.access.models import Organization, Recipient, Role, User


API_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = API_ROOT.parents[1]


def _load_demo_settings(*, environment="local", database_path=None):
    path = database_path or PROJECT_ROOT / "artifacts" / "demo" / "db.sqlite3"
    script = "import config.settings_demo as settings; print(settings.DATABASES['default']['NAME'])"
    env = os.environ.copy()
    env.update(
        {
            "ENVIRONMENT": environment,
            "SPLITBIND_DEMO_MODE": "true",
            "SPLITBIND_DEMO_DATABASE_PATH": str(path),
            "DJANGO_SECRET_KEY": "synthetic-demo-secret-for-settings-test",
            "OBJECT_STORAGE_ENDPOINT": "http://127.0.0.1:9000",
            "OBJECT_STORAGE_BUCKET": "splitbind-demo",
            "OBJECT_STORAGE_ACCESS_KEY": "synthetic-access",
            "OBJECT_STORAGE_SECRET_KEY": "synthetic-secret",
        }
    )
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=API_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_demo_settings_are_local_http_and_use_only_the_dedicated_database():
    database_path = PROJECT_ROOT / "artifacts" / "demo" / "db.sqlite3"
    script = """
import json
import config.settings_demo as settings
print(json.dumps({
    "environment": settings.ENVIRONMENT,
    "demo": settings.SPLITBIND_DEMO_MODE,
    "database": settings.DATABASES["default"],
    "hosts": settings.ALLOWED_HOSTS,
    "session_secure": settings.SESSION_COOKIE_SECURE,
    "csrf_secure": settings.CSRF_COOKIE_SECURE,
}))
"""
    env = os.environ.copy()
    env.update(
        {
            "ENVIRONMENT": "local",
            "SPLITBIND_DEMO_MODE": "true",
            "SPLITBIND_DEMO_DATABASE_PATH": str(database_path),
            "DJANGO_SECRET_KEY": "synthetic-demo-secret-for-settings-test",
            "OBJECT_STORAGE_ENDPOINT": "http://127.0.0.1:9000",
            "OBJECT_STORAGE_BUCKET": "splitbind-demo",
            "OBJECT_STORAGE_ACCESS_KEY": "synthetic-access",
            "OBJECT_STORAGE_SECRET_KEY": "synthetic-secret",
        }
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=API_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    import json

    observed = json.loads(result.stdout)
    assert observed == {
        "environment": "local",
        "demo": True,
        "database": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(database_path.resolve()),
        },
        "hosts": ["127.0.0.1", "localhost"],
        "session_secure": False,
        "csrf_secure": False,
    }


@pytest.mark.parametrize(
    ("environment", "database_path", "message"),
    [
        ("production", None, "local presentation settings require ENVIRONMENT=local"),
        ("local", PROJECT_ROOT / "outside.sqlite3", "must stay inside artifacts/demo"),
    ],
)
def test_demo_settings_fail_closed_outside_the_local_presentation_boundary(
    environment, database_path, message
):
    result = _load_demo_settings(environment=environment, database_path=database_path)

    assert result.returncode != 0
    assert message in result.stderr


@pytest.mark.django_db
@override_settings(ENVIRONMENT="local", SPLITBIND_DEMO_MODE=True)
def test_seed_demo_is_idempotent_and_keeps_synthetic_identity(monkeypatch):
    monkeypatch.setenv("SPLITBIND_DEMO_LOGIN_PASSWORD", "Synthetic-demo-password-123")
    first = io.StringIO()
    second = io.StringIO()

    call_command("seed_demo", stdout=first)
    call_command("seed_demo", stdout=second)

    organization = Organization.objects.get(slug="splitbind-demo")
    user = User.objects.get(username="demo-admin")
    recipient = Recipient.objects.get(
        organization=organization,
        external_reference="synthetic-recipient-001",
    )
    assert user.organization == organization
    assert user.role == Role.ADMINISTRATOR
    assert user.is_superuser is False
    assert user.check_password("Synthetic-demo-password-123")
    assert recipient.display_name == "Người nhận tổng hợp 001"
    assert Organization.objects.filter(slug="splitbind-demo").count() == 1
    assert User.objects.filter(username="demo-admin").count() == 1
    assert Recipient.objects.filter(
        organization=organization,
        external_reference="synthetic-recipient-001",
    ).count() == 1
    assert str(recipient.id) in first.getvalue()
    assert str(recipient.id) in second.getvalue()


@pytest.mark.django_db
@override_settings(ENVIRONMENT="local", SPLITBIND_DEMO_MODE=True)
def test_seed_demo_requires_an_explicit_password(monkeypatch):
    monkeypatch.delenv("SPLITBIND_DEMO_LOGIN_PASSWORD", raising=False)

    with pytest.raises(Exception, match="SPLITBIND_DEMO_LOGIN_PASSWORD_REQUIRED"):
        call_command("seed_demo", stdout=io.StringIO())


@pytest.mark.django_db
@override_settings(ENVIRONMENT="local", SPLITBIND_DEMO_MODE=True)
def test_seed_demo_reactivates_the_canonical_synthetic_administrator(monkeypatch):
    monkeypatch.setenv("SPLITBIND_DEMO_LOGIN_PASSWORD", "Replacement-password-123")
    organization = Organization.objects.create(
        slug="splitbind-demo", name="SplitBind Synthetic Demo"
    )
    user = User.objects.create_user(
        username="demo-admin",
        password="Old-password-123",
        organization=organization,
        role=Role.ADMINISTRATOR,
    )
    user.is_active = False
    user.save(update_fields=["is_active"])

    call_command("seed_demo", stdout=io.StringIO())

    user.refresh_from_db()
    assert user.is_active is True
    assert user.check_password("Replacement-password-123")


@pytest.mark.django_db
@override_settings(ENVIRONMENT="local", SPLITBIND_DEMO_MODE=True)
def test_seed_demo_organization_name_conflict_rolls_back_password(monkeypatch):
    monkeypatch.setenv("SPLITBIND_DEMO_LOGIN_PASSWORD", "Replacement-password-123")
    organization = Organization.objects.create(
        slug="splitbind-demo", name="Not the canonical synthetic organization"
    )
    user = User.objects.create_user(
        username="demo-admin",
        password="Old-password-123",
        organization=organization,
        role=Role.ADMINISTRATOR,
    )

    with pytest.raises(Exception, match="DEMO_SEED_CONFLICT"):
        call_command("seed_demo", stdout=io.StringIO())

    user.refresh_from_db()
    assert user.check_password("Old-password-123")
    assert organization.name == "Not the canonical synthetic organization"
    assert Recipient.objects.filter(organization=organization).count() == 0
