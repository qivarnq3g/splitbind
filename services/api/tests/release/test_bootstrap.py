import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from splitbind.access.models import Organization, Role, User


@pytest.mark.django_db
@override_settings(ENVIRONMENT="production", SPLITBIND_RELEASE_MODE="integrity_v1")
def test_bootstrap_integrity_release_creates_one_administrator(monkeypatch):
    monkeypatch.setenv("SPLITBIND_BOOTSTRAP_PASSWORD", "production-test-password-42")

    call_command(
        "bootstrap_integrity_release",
        organization_name="SplitBind",
        organization_slug="splitbind",
        username="admin",
    )

    organization = Organization.objects.get(slug="splitbind")
    user = User.objects.get(username="admin")
    assert organization.name == "SplitBind"
    assert user.organization_id == organization.id
    assert user.role == Role.ADMINISTRATOR
    assert user.is_staff is True
    assert user.is_superuser is True
    assert user.check_password("production-test-password-42")


@pytest.mark.django_db
@override_settings(ENVIRONMENT="production", SPLITBIND_RELEASE_MODE="integrity_v1")
def test_bootstrap_integrity_release_is_idempotent_without_resetting_password(monkeypatch):
    monkeypatch.setenv("SPLITBIND_BOOTSTRAP_PASSWORD", "production-test-password-42")
    options = {
        "organization_name": "SplitBind",
        "organization_slug": "splitbind",
        "username": "admin",
    }
    call_command("bootstrap_integrity_release", **options)
    monkeypatch.setenv("SPLITBIND_BOOTSTRAP_PASSWORD", "different-password-42")

    call_command("bootstrap_integrity_release", **options)

    assert Organization.objects.count() == 1
    assert User.objects.count() == 1
    assert User.objects.get(username="admin").check_password(
        "production-test-password-42"
    )


@pytest.mark.django_db
@override_settings(ENVIRONMENT="production", SPLITBIND_RELEASE_MODE="integrity_v1")
def test_bootstrap_integrity_release_rejects_identity_conflicts(monkeypatch):
    Organization.objects.create(name="Another tenant", slug="splitbind")
    monkeypatch.setenv("SPLITBIND_BOOTSTRAP_PASSWORD", "production-test-password-42")

    with pytest.raises(CommandError, match="BOOTSTRAP_IDENTITY_CONFLICT"):
        call_command(
            "bootstrap_integrity_release",
            organization_name="SplitBind",
            organization_slug="splitbind",
            username="admin",
        )
    assert User.objects.count() == 0


@pytest.mark.django_db
def test_bootstrap_integrity_release_rejects_nonproduction(monkeypatch):
    monkeypatch.setenv("SPLITBIND_BOOTSTRAP_PASSWORD", "production-test-password-42")

    with pytest.raises(CommandError, match="INTEGRITY_RELEASE_REQUIRED"):
        call_command(
            "bootstrap_integrity_release",
            organization_name="SplitBind",
            organization_slug="splitbind",
            username="admin",
        )
