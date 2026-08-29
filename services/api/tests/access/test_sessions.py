import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings

from splitbind.access.models import Organization, Role


@pytest.fixture
def organization(db):
    return Organization.objects.create(name="Session Organization", slug="session-org")


@pytest.fixture
def issuer(organization):
    return get_user_model().objects.create_user(
        username="session-issuer",
        password="correct-horse-battery-staple",
        organization=organization,
        role=Role.ISSUER,
    )


@pytest.fixture
def browser_client():
    return Client(enforce_csrf_checks=True)


def csrf_headers(client):
    response = client.get("/api/v1/auth/session")
    assert response.status_code == 200
    return {"HTTP_X_CSRFTOKEN": response.json()["csrf_token"]}


@pytest.mark.django_db
def test_session_bootstrap_is_public_but_business_defaults_are_authenticated(browser_client):
    bootstrap = browser_client.get("/api/v1/auth/session")

    assert bootstrap.status_code == 200
    assert bootstrap.json() == {"authenticated": False, "csrf_token": bootstrap.json()["csrf_token"]}
    assert "csrftoken" in bootstrap.cookies
    assert browser_client.get("/api/v1/audit-events").status_code == 403


@pytest.mark.django_db
def test_login_rotates_session_and_returns_only_safe_actor_fields(browser_client, issuer):
    session = browser_client.session
    session["pre_login"] = "synthetic"
    session.save()
    previous_key = session.session_key

    response = browser_client.post(
        "/api/v1/auth/login",
        data=json.dumps({"username": issuer.username, "password": "correct-horse-battery-staple"}),
        content_type="application/json",
        **csrf_headers(browser_client),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["authenticated"] is True
    assert payload["user"] == {
        "id": str(issuer.id),
        "username": issuer.username,
        "role": Role.ISSUER,
        "organization_id": str(issuer.organization_id),
    }
    assert "password" not in str(payload).lower()
    assert "sessionid" not in str(payload).lower()
    assert browser_client.session.session_key != previous_key


@pytest.mark.django_db
def test_login_error_is_generic_and_logout_requires_csrf(browser_client, issuer):
    issuer.is_active = False
    issuer.save(update_fields=["is_active"])
    missing = browser_client.post(
        "/api/v1/auth/login",
        data=json.dumps({"username": "not-an-account", "password": "wrong"}),
        content_type="application/json",
        **csrf_headers(browser_client),
    )
    inactive = browser_client.post(
        "/api/v1/auth/login",
        data=json.dumps({"username": issuer.username, "password": "correct-horse-battery-staple"}),
        content_type="application/json",
        **csrf_headers(browser_client),
    )

    assert missing.status_code == inactive.status_code
    assert missing.json() == inactive.json()

    issuer.is_active = True
    issuer.save(update_fields=["is_active"])

    login = browser_client.post(
        "/api/v1/auth/login",
        data=json.dumps({"username": issuer.username, "password": "correct-horse-battery-staple"}),
        content_type="application/json",
        **csrf_headers(browser_client),
    )
    assert login.status_code == 200
    assert browser_client.post("/api/v1/auth/logout").status_code == 403
    assert browser_client.post("/api/v1/auth/logout", **csrf_headers(browser_client)).status_code == 200
    assert browser_client.get("/api/v1/auth/session").json()["authenticated"] is False


@pytest.mark.django_db
@override_settings(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", CSRF_COOKIE_SECURE=True)
def test_production_cookie_attributes_are_secure(browser_client, issuer):
    csrf_response = browser_client.get("/api/v1/auth/session")
    login = browser_client.post(
        "/api/v1/auth/login",
        data=json.dumps({"username": issuer.username, "password": "correct-horse-battery-staple"}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf_response.json()["csrf_token"],
    )

    assert csrf_response.cookies["csrftoken"]["secure"] is True
    assert csrf_response.cookies["csrftoken"]["httponly"] == ""
    assert login.cookies["sessionid"]["secure"] is True
    assert login.cookies["sessionid"]["httponly"] is True
    assert login.cookies["sessionid"]["samesite"] == "Lax"
