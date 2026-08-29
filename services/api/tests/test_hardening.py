import uuid

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.utils import timezone

from splitbind.access.models import (
    Organization,
    Recipient,
    Role,
    SigningKey,
    ValidatedOrganizationOwnedModel,
)
from splitbind.audit.models import AuditEvent
from splitbind.documents.models import Document, Issuance, Manifest, Verification
from splitbind.jobs.models import Job, JobKind, JobResultReceipt
from splitbind.outbox.models import OutboxEvent
from splitbind.uploads.models import UploadPurpose, UploadRequest


SHA256 = "a" * 64


@pytest.fixture
def tenant_pair(db):
    first = Organization.objects.create(name="First Organization", slug="first")
    second = Organization.objects.create(name="Second Organization", slug="second")
    first_user = get_user_model().objects.create_user(
        username="first-user",
        password="test-password-not-a-secret",
        organization=first,
        role=Role.ISSUER,
    )
    second_user = get_user_model().objects.create_user(
        username="second-user",
        password="test-password-not-a-secret",
        organization=second,
        role=Role.ISSUER,
    )
    first_upload = UploadRequest.objects.create(
        organization=first,
        requested_by=first_user,
        purpose=UploadPurpose.ISSUANCE,
        object_key="first/source.pdf",
        sha256=SHA256,
        size_bytes=1,
        expires_at=timezone.now(),
    )
    first_document = Document.objects.create(
        organization=first,
        created_by=first_user,
        upload_request=first_upload,
        source_object_key="first/document.pdf",
        source_sha256=SHA256,
        page_count=1,
    )
    second_upload = UploadRequest.objects.create(
        organization=second,
        requested_by=second_user,
        purpose=UploadPurpose.ISSUANCE,
        object_key="second/source.pdf",
        sha256=SHA256,
        size_bytes=1,
        expires_at=timezone.now(),
    )
    second_document = Document.objects.create(
        organization=second,
        created_by=second_user,
        upload_request=second_upload,
        source_object_key="second/document.pdf",
        source_sha256=SHA256,
        page_count=1,
    )
    second_recipient = Recipient.objects.create(
        organization=second,
        external_reference="second-recipient",
        display_name="Second Recipient",
    )
    second_issuance = Issuance.objects.create(
        organization=second,
        created_by=second_user,
        document=second_document,
        recipient=second_recipient,
    )
    second_job = Job.objects.create(
        organization=second,
        kind=JobKind.ISSUANCE,
        issuance=second_issuance,
        deadline_at=timezone.now(),
        correlation_id=uuid.uuid4(),
    )
    second_signing_key = SigningKey.objects.create(
        organization=second,
        key_id="second-signing-key",
        public_key="synthetic-public-key",
        valid_from=timezone.now(),
    )
    return {
        "first": first,
        "first_document": first_document,
        "first_upload": first_upload,
        "first_user": first_user,
        "second": second,
        "second_job": second_job,
        "second_signing_key": second_signing_key,
        "second_user": second_user,
    }


def test_tenant_bound_models_share_the_validated_persistence_boundary():
    models = [
        get_user_model(),
        UploadRequest,
        Recipient,
        SigningKey,
        Document,
        Issuance,
        Manifest,
        Verification,
        Job,
        JobResultReceipt,
        OutboxEvent,
        AuditEvent,
    ]

    assert all(issubclass(model, ValidatedOrganizationOwnedModel) for model in models)


def test_objects_create_and_save_reject_cross_tenant_relations(tenant_pair):
    first = tenant_pair["first"]
    first_document = tenant_pair["first_document"]
    first_upload = tenant_pair["first_upload"]
    first_user = tenant_pair["first_user"]
    second_job = tenant_pair["second_job"]
    second_signing_key = tenant_pair["second_signing_key"]
    second_user = tenant_pair["second_user"]

    with pytest.raises(ValidationError, match="same organization"):
        UploadRequest.objects.create(
            organization=first,
            requested_by=second_user,
            purpose=UploadPurpose.ISSUANCE,
            object_key="first/cross-upload.pdf",
            expires_at=timezone.now(),
        )

    cross_document = Document(
        organization=first,
        created_by=second_user,
        upload_request=first_upload,
        source_object_key="first/cross-document.pdf",
        source_sha256=SHA256,
        page_count=1,
    )
    with pytest.raises(ValidationError, match="same organization"):
        cross_document.save()

    with pytest.raises(ValidationError, match="same organization"):
        Manifest.objects.create(
            organization=first,
            issuance=Issuance.objects.create(
                organization=first,
                created_by=first_user,
                document=first_document,
                recipient=Recipient.objects.create(
                    organization=first,
                    external_reference="first-recipient",
                    display_name="First Recipient",
                ),
            ),
            signing_key=second_signing_key,
            internal_payload="{}",
            internal_signature_envelope={},
            public_payload="{}",
            public_signature_envelope={},
        )

    with pytest.raises(ValidationError, match="same organization"):
        OutboxEvent.objects.create(
            organization=first,
            message_id=uuid.uuid4(),
            job=second_job,
            attempt=0,
            topic="issuance.requested",
        )

    with pytest.raises(ValidationError, match="same organization"):
        AuditEvent.objects.create(
            organization=first,
            actor=second_user,
            action="test.cross_tenant",
            target_type="document",
            target_id=str(first_document.id),
            correlation_id=uuid.uuid4(),
            outcome="denied",
        )


def test_bulk_policy_rejects_tenant_or_relation_mutations_but_allows_state_updates(
    tenant_pair,
):
    first = tenant_pair["first"]
    second = tenant_pair["second"]
    first_upload = tenant_pair["first_upload"]
    first_user = tenant_pair["first_user"]
    second_user = tenant_pair["second_user"]

    with pytest.raises(ValidationError, match="bulk update"):
        get_user_model().objects.filter(pk=first_user.pk).update(organization=second)
    with pytest.raises(ValidationError, match="bulk update"):
        UploadRequest.objects.filter(pk=first_upload.pk).update(organization=second)
    with pytest.raises(ValidationError, match="bulk update"):
        UploadRequest.objects.filter(pk=first_upload.pk).update(requested_by=second_user)

    assert UploadRequest.objects.filter(pk=first_upload.pk).update(finalized_at=timezone.now()) == 1


def test_user_manager_requires_tenant_and_prevents_privilege_conflicts(db):
    user_model = get_user_model()
    organization = Organization.objects.create(name="Manager Organization", slug="manager")

    with pytest.raises(ValueError, match="organization"):
        user_model.objects.create_user(username="missing-org", password="password")
    with pytest.raises(ValueError, match="is_superuser"):
        user_model.objects.create_user(
            username="wrong-user",
            password="password",
            organization=organization,
            role=Role.ISSUER,
            is_superuser=True,
        )
    with pytest.raises(ValueError, match="administrator"):
        user_model.objects.create_superuser(
            username="wrong-admin",
            password="password",
            organization=organization,
            role=Role.ISSUER,
        )


def test_createsuperuser_command_uses_tenant_and_administrator_role(db, monkeypatch):
    organization = Organization.objects.create(name="CLI Organization", slug="cli")
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "test-password-not-a-secret")

    call_command(
        "createsuperuser",
        username="cli-admin",
        organization=str(organization.id),
        interactive=False,
    )

    user = get_user_model().objects.get(username="cli-admin")
    assert user.organization_id == organization.id
    assert user.role == Role.ADMINISTRATOR
    assert user.is_staff is True
    assert user.is_superuser is True
