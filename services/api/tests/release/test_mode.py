import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import Client, override_settings

from splitbind.access.models import Organization, Role, User
from splitbind.release.mode import ReleaseMode, load_release_mode


def test_production_accepts_only_integrity_v1():
    assert load_release_mode("production", "integrity_v1") is ReleaseMode.INTEGRITY_V1

    with pytest.raises(ImproperlyConfigured):
        load_release_mode("production", "experimental_fingerprint")


def test_production_requires_an_explicit_release_mode():
    with pytest.raises(ImproperlyConfigured):
        load_release_mode("production", None)


@pytest.mark.parametrize("environment", ["test", "local", "offline"])
def test_nonproduction_may_leave_release_mode_disabled(environment):
    assert load_release_mode(environment, None) is None


@pytest.mark.django_db
@override_settings(
    SPLITBIND_DEMO_MODE=False,
    SPLITBIND_RELEASE_MODE=ReleaseMode.INTEGRITY_V1,
)
def test_integrity_capability_never_claims_hidden_or_transformed_attribution():
    organization = Organization.objects.create(name="Release", slug="release")
    user = User.objects.create_user(
        username="release-issuer",
        password="correct horse battery staple",
        organization=organization,
        role=Role.ISSUER,
    )
    client = Client()
    client.force_login(user)

    response = client.get("/api/v1/demo/capabilities")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
        "processing_limits": {
            "max_pdf_pages": 5,
            "max_pdf_bytes": 10 * 1024 * 1024,
            "max_image_pixels": 40_000_000,
        },
        "algorithm_label": "integrity_release_v1",
        "hidden_fingerprint_enabled": False,
        "transformed_attribution_available": False,
    }
