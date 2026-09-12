import uuid
from datetime import timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.test import override_settings
from django.utils import timezone

from splitbind.access.models import Organization, SigningKey
from splitbind.release.mode import ReleaseMode


def public_pem():
    return Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")


STORAGE = {
    "ENVIRONMENT": "test",
    "OBJECT_STORAGE_ENDPOINT": "http://minio:9000",
    "OBJECT_STORAGE_ENDPOINT_HINT": "",
    "OBJECT_STORAGE_BUCKET": "bucket",
    "OBJECT_STORAGE_ACCESS_KEY": "fake-access",
    "OBJECT_STORAGE_SECRET_KEY": "fake-secret",
}


@pytest.mark.django_db
def test_readiness_is_public_safe_and_up_only_with_all_real_components(client):
    now = timezone.now()
    org = Organization.objects.create(name="Ready", slug=f"ready-{uuid.uuid4().hex[:8]}")
    SigningKey.objects.create(
        organization=org, key_id="ready-key", public_key=public_pem(),
        valid_from=now - timedelta(minutes=1), valid_until=now + timedelta(minutes=1),
    )
    with override_settings(
        SPLITBIND_BROKER_READINESS=lambda *, timeout_seconds: True,
        **STORAGE,
    ):
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "components": {
            "database": "up",
            "broker": "up",
            "storage_config": "up",
            "public_key_registry": "up",
        },
    }


@pytest.mark.django_db
def test_missing_broker_probe_fails_closed_without_configuration_details(client):
    with override_settings(SPLITBIND_BROKER_READINESS=None, **STORAGE):
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["components"]["broker"] == "down"
    serialized = response.content.decode().lower()
    for forbidden in ("exception", "credential", "endpoint", "key_id", "object"):
        assert forbidden not in serialized


@pytest.mark.django_db
def test_readiness_checks_components_independently_and_never_accesses_storage_objects(client, monkeypatch):
    calls = []

    class StorageTrap:
        def head(self, **kwargs):
            calls.append("head")
            raise AssertionError

        def presign_get(self, **kwargs):
            calls.append("get")
            raise AssertionError

        def delete(self, **kwargs):
            calls.append("delete")
            raise AssertionError

    with override_settings(
        SPLITBIND_BROKER_READINESS=lambda *, timeout_seconds: (_ for _ in ()).throw(TimeoutError()),
        SPLITBIND_OBJECT_STORAGE=StorageTrap(),
        **STORAGE,
    ):
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["components"]["broker"] == "down"
    assert calls == []


@pytest.mark.django_db
def test_liveness_remains_zero_query_while_readiness_executes_database_probe(client, django_assert_num_queries):
    with django_assert_num_queries(0):
        assert client.get("/health/live").status_code == 200
    with override_settings(SPLITBIND_BROKER_READINESS=None, **STORAGE):
        with django_assert_num_queries(2):
            assert client.get("/health/ready").status_code == 503


@pytest.mark.django_db
def test_integrity_release_reports_the_broker_as_not_applicable_and_stays_ready(client):
    now = timezone.now()
    org = Organization.objects.create(name="Integrity", slug=f"integrity-{uuid.uuid4().hex[:8]}")
    SigningKey.objects.create(
        organization=org, key_id="integrity-key", public_key=public_pem(),
        valid_from=now - timedelta(minutes=1), valid_until=now + timedelta(minutes=1),
    )
    with override_settings(
        SPLITBIND_RELEASE_MODE=ReleaseMode.INTEGRITY_V1,
        SPLITBIND_BROKER_READINESS=None,
        **STORAGE,
    ):
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "components": {
            "database": "up",
            "broker": "not_applicable",
            "storage_config": "up",
            "public_key_registry": "up",
        },
    }


@pytest.mark.django_db
def test_integrity_release_still_fails_closed_when_a_real_component_is_down(client):
    with override_settings(
        SPLITBIND_RELEASE_MODE=ReleaseMode.INTEGRITY_V1,
        SPLITBIND_BROKER_READINESS=None,
        **STORAGE,
    ):
        response = client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["components"]["broker"] == "not_applicable"
    assert body["components"]["public_key_registry"] == "down"


@pytest.mark.django_db
def test_integrity_release_never_probes_a_broker_it_does_not_have(client):
    probed = []

    def trap(*, timeout_seconds):
        probed.append(timeout_seconds)
        return True

    with override_settings(
        SPLITBIND_RELEASE_MODE=ReleaseMode.INTEGRITY_V1,
        SPLITBIND_BROKER_READINESS=trap,
        **STORAGE,
    ):
        client.get("/health/ready")

    assert probed == []
