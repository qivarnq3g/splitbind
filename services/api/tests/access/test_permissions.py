import json
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from splitbind.access.models import Organization, Recipient, Role
from splitbind.access.permissions import IsAdministrator, IsAuditor, IsIssuer, IsVerifier
from splitbind.access.selectors import scope_issuances, scope_verifications
from splitbind.documents.models import Document, Issuance, Verification
from splitbind.uploads.models import UploadPurpose, UploadRequest


SHA256 = "a" * 64


def create_user(organization, role, suffix):
    return get_user_model().objects.create_user(
        username=f"{role}-{suffix}",
        password="test-password-not-a-secret",
        organization=organization,
        role=role,
    )


def create_issuance(organization, actor, suffix):
    upload = UploadRequest.objects.create(
        organization=organization,
        requested_by=actor,
        purpose=UploadPurpose.ISSUANCE,
        object_key=f"{organization.slug}/{suffix}/source.pdf",
        sha256=SHA256,
        size_bytes=1,
        expires_at="2030-01-01T00:00:00Z",
    )
    document = Document.objects.create(
        organization=organization,
        created_by=actor,
        upload_request=upload,
        source_object_key=f"{organization.slug}/{suffix}/document.pdf",
        source_sha256=SHA256,
        page_count=1,
    )
    recipient = Recipient.objects.create(
        organization=organization,
        external_reference=f"recipient-{suffix}",
        display_name="Synthetic Recipient",
    )
    return Issuance.objects.create(
        organization=organization,
        created_by=actor,
        document=document,
        recipient=recipient,
    )


def create_verification(organization, actor, suffix):
    upload = UploadRequest.objects.create(
        organization=organization,
        requested_by=actor,
        purpose=UploadPurpose.VERIFICATION,
        object_key=f"{organization.slug}/{suffix}/suspect.png",
        sha256=SHA256,
        size_bytes=1,
        expires_at="2030-01-01T00:00:00Z",
    )
    return Verification.objects.create(
        organization=organization,
        requested_by=actor,
        upload_request=upload,
    )


@pytest.mark.django_db
def test_all_roles_receive_only_their_documented_organization_scope():
    organization = Organization.objects.create(name="Primary", slug="primary")
    foreign_organization = Organization.objects.create(name="Foreign", slug="foreign")
    admin = create_user(organization, Role.ADMINISTRATOR, "admin")
    issuer = create_user(organization, Role.ISSUER, "issuer")
    other_issuer = create_user(organization, Role.ISSUER, "other-issuer")
    verifier = create_user(organization, Role.VERIFIER, "verifier")
    other_verifier = create_user(organization, Role.VERIFIER, "other-verifier")
    auditor = create_user(organization, Role.AUDITOR, "auditor")
    foreign_issuer = create_user(foreign_organization, Role.ISSUER, "foreign")

    owned_issuance = create_issuance(organization, issuer, "owned")
    other_issuance = create_issuance(organization, other_issuer, "other")
    foreign_issuance = create_issuance(foreign_organization, foreign_issuer, "foreign")
    owned_verification = create_verification(organization, verifier, "owned")
    other_verification = create_verification(organization, other_verifier, "other")

    assert set(scope_issuances(admin, Issuance.objects.all())) == {owned_issuance, other_issuance}
    assert set(scope_issuances(auditor, Issuance.objects.all())) == {owned_issuance, other_issuance}
    assert list(scope_issuances(issuer, Issuance.objects.all())) == [owned_issuance]
    assert not scope_issuances(verifier, Issuance.objects.all()).exists()
    assert foreign_issuance not in scope_issuances(admin, Issuance.objects.all())

    assert set(scope_verifications(admin, Verification.objects.all())) == {owned_verification, other_verification}
    assert set(scope_verifications(auditor, Verification.objects.all())) == {owned_verification, other_verification}
    assert list(scope_verifications(verifier, Verification.objects.all())) == [owned_verification]
    assert not scope_verifications(issuer, Verification.objects.all()).exists()


def test_role_permissions_are_exact_and_auditor_is_read_only(rf):
    request = rf.get("/")
    request.user = type("Actor", (), {"role": Role.AUDITOR, "is_authenticated": True})()

    assert IsAuditor().has_permission(request, None) is True
    assert IsAdministrator().has_permission(request, None) is False
    assert IsIssuer().has_permission(request, None) is False
    assert IsVerifier().has_permission(request, None) is False

    request.user.role = Role.ADMINISTRATOR
    assert IsAdministrator().has_permission(request, None) is True


@pytest.mark.django_db
def test_audit_list_is_org_scoped_and_auditor_has_no_mutation_route():
    organization = Organization.objects.create(name="Audit Primary", slug="audit-primary")
    foreign_organization = Organization.objects.create(name="Audit Foreign", slug="audit-foreign")
    auditor = create_user(organization, Role.AUDITOR, "reader")
    issuer = create_user(organization, Role.ISSUER, "writer")
    foreign_auditor = create_user(foreign_organization, Role.AUDITOR, "foreign-reader")

    from splitbind.audit.models import AuditOutcome
    from splitbind.audit.services import record_event

    record_event(auditor, "audit.read", auditor, AuditOutcome.SUCCEEDED, uuid.uuid4(), {"kind": "read"})
    record_event(
        foreign_auditor,
        "audit.read",
        foreign_auditor,
        AuditOutcome.SUCCEEDED,
        uuid.uuid4(),
        {"kind": "read"},
    )

    client = Client(enforce_csrf_checks=True)
    assert client.login(username=auditor.username, password="test-password-not-a-secret")
    listed = client.get("/api/v1/audit-events")
    assert listed.status_code == 200
    assert [event["actor_id"] for event in listed.json()["results"]] == [str(auditor.id)]
    csrf = client.get("/api/v1/auth/session").json()["csrf_token"]
    assert client.post(
        "/api/v1/audit-events",
        data=json.dumps({}),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
    ).status_code == 405

    client.logout()
    assert client.login(username=issuer.username, password="test-password-not-a-secret")
    assert client.get("/api/v1/audit-events").status_code == 403


@pytest.mark.django_db
def test_administrator_account_management_uses_protected_django_admin():
    organization = Organization.objects.create(name="Administration", slug="administration")
    foreign_organization = Organization.objects.create(name="Other Administration", slug="other-administration")
    administrator = create_user(organization, Role.ADMINISTRATOR, "accounts")
    issuer = create_user(organization, Role.ISSUER, "no-admin")
    foreign_user = create_user(foreign_organization, Role.ISSUER, "foreign-account")

    client = Client()
    assert client.login(username=administrator.username, password="test-password-not-a-secret")
    assert administrator.is_staff is True
    assert client.get("/admin/access/user/").status_code == 200
    foreign_detail = client.get(f"/admin/access/user/{foreign_user.pk}/change/")
    assert foreign_detail.status_code in {302, 404}
    assert foreign_user.username.encode() not in foreign_detail.content

    client.logout()
    assert client.login(username=issuer.username, password="test-password-not-a-secret")
    assert client.get("/admin/access/user/").status_code == 302


@pytest.mark.django_db
def test_organization_administrator_cannot_manage_a_superuser_account():
    organization = Organization.objects.create(name="Protected Administration", slug="protected-administration")
    administrator = create_user(organization, Role.ADMINISTRATOR, "protected-accounts")
    superuser = get_user_model().objects.create_superuser(
        username="protected-root",
        password="test-password-not-a-secret",
        organization=organization,
    )

    client = Client()
    assert client.login(username=administrator.username, password="test-password-not-a-secret")

    response = client.get(f"/admin/access/user/{superuser.pk}/change/")

    assert response.status_code in {302, 404}
    assert superuser.username.encode() not in response.content
