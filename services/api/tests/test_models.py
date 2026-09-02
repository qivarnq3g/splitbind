import uuid

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.loader import MigrationLoader
from django.db.models import BinaryField
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from splitbind.access.models import Organization, Recipient, Role, SigningKey
from splitbind.audit.models import AuditEvent, AuditOutcome
from splitbind.audit.services import record_event
from splitbind.documents.models import (
    Document,
    Issuance,
    Manifest,
    Verification,
    VerificationStatus,
)
from splitbind.demo.models import DemoIssuanceResult
from splitbind.jobs.models import Job, JobKind, JobResultReceipt, JobStatus
from splitbind.outbox.models import OutboxEvent
from splitbind.uploads.models import UploadPurpose, UploadRequest


SHA256_A = "a" * 64
SHA256_B = "b" * 64
PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAAAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=
-----END PUBLIC KEY-----
"""


@pytest.fixture
def organization(db):
    return Organization.objects.create(name="Example Organization", slug="example")


@pytest.fixture
def user(organization):
    return get_user_model().objects.create_user(
        username="issuer",
        password="test-password-not-a-secret",
        organization=organization,
        role=Role.ISSUER,
    )


@pytest.fixture
def recipient(organization):
    return Recipient.objects.create(
        organization=organization,
        external_reference="recipient-001",
        display_name="Synthetic Recipient",
    )


@pytest.fixture
def upload_request(organization, user):
    return UploadRequest.objects.create(
        organization=organization,
        requested_by=user,
        purpose=UploadPurpose.ISSUANCE,
        object_key="org/example/uploads/source.pdf",
        expected_sha256=SHA256_A,
        size_bytes=1024,
        expires_at=timezone.now() + timezone.timedelta(minutes=15),
    )


@pytest.fixture
def document(organization, user, upload_request):
    return Document.objects.create(
        organization=organization,
        created_by=user,
        upload_request=upload_request,
        source_object_key=upload_request.object_key,
        expected_source_sha256=SHA256_A,
        page_count=1,
    )


@pytest.fixture
def issuance(organization, user, recipient, document):
    return Issuance.objects.create(
        organization=organization,
        created_by=user,
        recipient=recipient,
        document=document,
        output_object_key="org/example/issuances/output.pdf",
        output_sha256=SHA256_B,
    )


@pytest.fixture
def signing_key(organization):
    return SigningKey.objects.create(
        organization=organization,
        key_id="manifest-ed25519-2026-01",
        public_key=PUBLIC_KEY_PEM,
        valid_from=timezone.now(),
    )


@pytest.fixture
def verification_upload(organization, user):
    return UploadRequest.objects.create(
        organization=organization,
        requested_by=user,
        purpose=UploadPurpose.VERIFICATION,
        object_key="org/example/uploads/suspect.png",
        expected_sha256=SHA256_B,
        size_bytes=2048,
        expires_at=timezone.now() + timezone.timedelta(minutes=15),
    )


@pytest.fixture
def verification(organization, user, verification_upload):
    return Verification.objects.create(
        organization=organization,
        requested_by=user,
        upload_request=verification_upload,
    )


@pytest.fixture
def job(organization, issuance):
    return Job.objects.create(
        organization=organization,
        kind=JobKind.ISSUANCE,
        issuance=issuance,
        attempt=0,
        deadline_at=timezone.now() + timezone.timedelta(minutes=10),
        correlation_id=uuid.uuid4(),
    )


def test_stable_role_and_status_values_are_exact():
    assert set(Role.values) == {"administrator", "issuer", "verifier", "auditor"}
    assert set(JobStatus.values) == {
        "created",
        "queued",
        "processing",
        "retryable_failed",
        "succeeded",
        "failed",
        "dead_lettered",
        "cancelled",
    }
    assert set(VerificationStatus.values) == {
        "VERIFIED_INTACT",
        "SOURCE_IDENTIFIED_MODIFIED",
        "PARTIAL_EVIDENCE",
        "NO_WATERMARK",
        "INVALID_MANIFEST",
        "PROCESSING_FAILED",
    }


@pytest.mark.django_db
def test_database_rejects_unknown_stable_enum_values(user, job, verification):
    checks = [
        (get_user_model().objects.filter(pk=user.pk), {"role": "unknown"}),
        (Job.objects.filter(pk=job.pk), {"status": "unknown"}),
        (Verification.objects.filter(pk=verification.pk), {"status": "unknown"}),
    ]

    for queryset, values in checks:
        with transaction.atomic(), pytest.raises(IntegrityError):
            queryset.update(**values)


@pytest.mark.django_db
def test_user_and_business_records_are_owned_by_one_organization(
    organization,
    user,
    recipient,
    upload_request,
    document,
    issuance,
    signing_key,
    verification,
    job,
):
    manifest = Manifest.objects.create(
        organization=organization,
        issuance=issuance,
        signing_key=signing_key,
        internal_payload='{"recipient_id":"internal"}',
        internal_signature_envelope={"algorithm": "Ed25519", "signature": "internal"},
        public_payload='{"issuance_id":"public"}',
        public_signature_envelope={"algorithm": "Ed25519", "signature": "public"},
    )
    receipt = JobResultReceipt.objects.create(
        organization=organization,
        message_id=uuid.uuid4(),
        job=job,
    )
    outbox = OutboxEvent.objects.create(
        organization=organization,
        message_id=uuid.uuid4(),
        job=job,
        attempt=job.attempt,
        topic="issuance.requested",
        payload={"schema_version": 1},
    )
    audit = record_event(
        user,
        "issuance.created",
        issuance,
        AuditOutcome.SUCCEEDED,
        job.correlation_id,
        {"status": "created"},
    )

    records = [
        user,
        recipient,
        upload_request,
        document,
        issuance,
        signing_key,
        verification,
        job,
        manifest,
        receipt,
        outbox,
        audit,
    ]
    assert all(record.organization_id == organization.id for record in records)


@pytest.mark.django_db
def test_api_resource_ids_default_to_random_uuid4(
    organization,
    user,
    recipient,
    upload_request,
    document,
    issuance,
    signing_key,
    verification,
    job,
):
    resources = [
        organization,
        user,
        recipient,
        upload_request,
        document,
        issuance,
        signing_key,
        verification,
        job,
    ]
    assert all(resource.id.version == 4 for resource in resources)
    assert len({resource.id for resource in resources}) == len(resources)


def test_issuance_id_is_random_uuid_and_recipient_is_internal(issuance):
    payload = issuance.public_payload()

    assert issuance.id.version == 4
    assert issuance.recipient_id is not None
    assert payload["issuance_id"] == str(issuance.id)
    assert not {
        "recipient",
        "recipient_id",
        "document_id",
        "source_object_key",
        "output_object_key",
    } & payload.keys()
    assert "Synthetic Recipient" not in str(payload)
    assert issuance.output_object_key not in str(payload)


def test_cross_organization_issuance_is_rejected_at_model_boundary(
    organization, user, document
):
    other = Organization.objects.create(name="Other Organization", slug="other")
    other_recipient = Recipient.objects.create(
        organization=other,
        external_reference="recipient-002",
        display_name="Other Synthetic Recipient",
    )
    cross_scoped = Issuance(
        organization=organization,
        created_by=user,
        document=document,
        recipient=other_recipient,
    )

    with pytest.raises(ValidationError, match="same organization"):
        cross_scoped.full_clean()


def test_model_boundaries_reject_cross_organization_relations(
    organization, upload_request, issuance
):
    other = Organization.objects.create(name="Other Organization", slug="other")
    other_user = get_user_model().objects.create_user(
        username="other-issuer",
        password="test-password-not-a-secret",
        organization=other,
        role=Role.ISSUER,
    )
    other_upload = UploadRequest.objects.create(
        organization=other,
        requested_by=other_user,
        purpose=UploadPurpose.ISSUANCE,
        object_key="org/other/uploads/source.pdf",
        expected_sha256=SHA256_A,
        size_bytes=1024,
        expires_at=timezone.now() + timezone.timedelta(minutes=15),
    )
    other_document = Document.objects.create(
        organization=other,
        created_by=other_user,
        upload_request=other_upload,
        source_object_key=other_upload.object_key,
        expected_source_sha256=SHA256_A,
        page_count=1,
    )
    other_recipient = Recipient.objects.create(
        organization=other,
        external_reference="recipient-002",
        display_name="Other Synthetic Recipient",
    )
    other_issuance = Issuance.objects.create(
        organization=other,
        created_by=other_user,
        recipient=other_recipient,
        document=other_document,
    )
    other_job = Job.objects.create(
        organization=other,
        kind=JobKind.ISSUANCE,
        issuance=other_issuance,
        deadline_at=timezone.now(),
        correlation_id=uuid.uuid4(),
    )
    other_signing_key = SigningKey.objects.create(
        organization=other,
        key_id="manifest-ed25519-other",
        public_key=PUBLIC_KEY_PEM,
        valid_from=timezone.now(),
    )
    checks = [
        UploadRequest(
            organization=organization,
            requested_by=other_user,
            purpose=UploadPurpose.ISSUANCE,
            object_key="org/example/uploads/cross-user.pdf",
            expected_sha256=SHA256_A,
            size_bytes=1,
            expires_at=timezone.now(),
        ),
        Document(
            organization=organization,
            created_by=other_user,
            upload_request=upload_request,
            source_object_key="org/example/uploads/cross-document.pdf",
            expected_source_sha256=SHA256_A,
            page_count=1,
        ),
        Manifest(
            organization=organization,
            issuance=issuance,
            signing_key=other_signing_key,
            internal_payload="{}",
            internal_signature_envelope={},
            public_payload="{}",
            public_signature_envelope={},
        ),
        Verification(
            organization=organization,
            requested_by=other_user,
            upload_request=upload_request,
        ),
        Job(
            organization=organization,
            kind=JobKind.ISSUANCE,
            issuance=other_issuance,
            deadline_at=timezone.now(),
            correlation_id=uuid.uuid4(),
        ),
        JobResultReceipt(
            organization=organization,
            message_id=uuid.uuid4(),
            job=other_job,
        ),
        OutboxEvent(
            organization=organization,
            message_id=uuid.uuid4(),
            job=other_job,
            attempt=other_job.attempt,
            topic="issuance.requested",
        ),
        AuditEvent(
            organization=organization,
            actor=other_user,
            action="issuance.created",
            target_type="issuance",
            target_id=str(issuance.id),
            correlation_id=uuid.uuid4(),
            outcome="succeeded",
        ),
    ]

    for record in checks:
        with pytest.raises(ValidationError, match="same organization"):
            record.full_clean()


@pytest.mark.parametrize("invalid_hash", ["a" * 63, "A" * 64, "g" * 64])
def test_sha256_validator_rejects_noncanonical_values(
    invalid_hash, organization, user, upload_request
):
    document = Document(
        organization=organization,
        created_by=user,
        upload_request=upload_request,
        source_object_key="org/example/uploads/invalid.pdf",
        expected_source_sha256=invalid_hash,
        page_count=1,
    )

    with pytest.raises(ValidationError):
        document.full_clean()


def test_sha256_database_constraint_rejects_noncanonical_value(
    organization, user, upload_request
):
    with pytest.raises(IntegrityError), transaction.atomic():
        Document.objects.create(
            organization=organization,
            created_by=user,
            upload_request=upload_request,
            source_object_key="org/example/uploads/uppercase.pdf",
            expected_source_sha256="A" * 64,
            page_count=1,
        )


def test_job_attempt_ceiling_is_enforced_by_model_and_database(job):
    job.attempt = 3
    with pytest.raises(ValidationError):
        job.full_clean()

    with pytest.raises(IntegrityError), transaction.atomic():
        job.save(update_fields=["attempt"])


def test_idempotency_keys_and_job_attempt_identity_are_unique(
    organization, job, signing_key
):
    receipt_message_id = uuid.uuid4()
    JobResultReceipt.objects.create(
        organization=organization,
        message_id=receipt_message_id,
        job=job,
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        JobResultReceipt.objects.create(
            organization=organization,
            message_id=receipt_message_id,
            job=job,
        )

    outbox_message_id = uuid.uuid4()
    OutboxEvent.objects.create(
        organization=organization,
        message_id=outbox_message_id,
        job=job,
        attempt=0,
        topic="issuance.requested",
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        OutboxEvent.objects.create(
            organization=organization,
            message_id=uuid.uuid4(),
            job=job,
            attempt=0,
            topic="issuance.requested",
        )

    with pytest.raises(IntegrityError), transaction.atomic():
        SigningKey.objects.create(
            organization=organization,
            key_id=signing_key.key_id,
            public_key=PUBLIC_KEY_PEM,
            valid_from=timezone.now(),
        )


def test_manifest_stores_separate_canonical_payloads_and_signature_envelopes(
    organization, issuance, signing_key
):
    manifest = Manifest.objects.create(
        organization=organization,
        issuance=issuance,
        signing_key=signing_key,
        internal_payload='{"recipient_id":"internal"}',
        internal_signature_envelope={"algorithm": "Ed25519", "signature": "sig-internal"},
        public_payload='{"issuance_id":"public"}',
        public_signature_envelope={"algorithm": "Ed25519", "signature": "sig-public"},
    )

    assert manifest.internal_payload != manifest.public_payload
    assert manifest.internal_signature_envelope != manifest.public_signature_envelope
    assert manifest.signing_key.key_id == "manifest-ed25519-2026-01"


def test_json_defaults_are_callable_and_not_shared(organization, user, verification_upload):
    first = Verification(
        organization=organization,
        requested_by=user,
        upload_request=verification_upload,
    )
    second = Verification(
        organization=organization,
        requested_by=user,
        upload_request=verification_upload,
    )

    first.evidence["fingerprint_confidence"] = 0.5
    first.metrics["processing_ms"] = 10

    assert second.evidence == {}
    assert second.metrics == {}


def test_historical_and_evidentiary_relations_are_protected(recipient, issuance):
    with pytest.raises(ProtectedError):
        recipient.delete()


def test_models_have_no_binary_or_private_key_fields():
    model_classes = [
        Organization,
        get_user_model(),
        Recipient,
        SigningKey,
        UploadRequest,
        Document,
        Issuance,
        Manifest,
        Verification,
        Job,
        JobResultReceipt,
        DemoIssuanceResult,
        OutboxEvent,
        AuditEvent,
    ]

    fields = [field for model in model_classes for field in model._meta.get_fields()]
    assert not any(isinstance(field, BinaryField) for field in fields)
    assert not any("private" in field.name or "secret" in field.name for field in fields)


def test_persisted_timestamps_are_timezone_aware(issuance, job):
    assert timezone.is_aware(issuance.issued_at)
    assert timezone.is_aware(job.created_at)


@pytest.mark.django_db
def test_initial_migration_graph_contains_every_domain_model():
    loader = MigrationLoader(connection, ignore_no_migrations=False)
    state = loader.project_state()
    expected = {
        "access": {"organization", "user", "recipient", "signingkey"},
        "uploads": {"uploadrequest"},
        "documents": {"document", "issuance", "manifest", "verification"},
        "jobs": {"job", "jobresultreceipt"},
        "demo": {"demoissuanceresult"},
        "outbox": {"outboxevent"},
        "audit": {"auditevent"},
    }

    for app_label, model_names in expected.items():
        assert (app_label, "0001_initial") in loader.disk_migrations
        migrated_names = {
            name for (label, name) in state.models if label == app_label
        }
        assert model_names <= migrated_names
