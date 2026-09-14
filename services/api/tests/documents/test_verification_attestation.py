import base64
import hashlib
import uuid
from datetime import timedelta

import pytest
import rfc8785
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.utils import timezone

from splitbind.access.models import Organization, Recipient, Role, SigningKey, User
from splitbind.documents.models import Document, Issuance, Manifest
from splitbind.documents.serializers import manifest_attestation
from splitbind.uploads.models import UploadPurpose, UploadRequest


OUTPUT_SHA256 = "b" * 64
ISSUED_AT = "2026-08-30T00:00:00Z"


def _signed(private, payload, key_id):
    canonical = rfc8785.dumps(payload)
    return canonical.decode("utf-8"), {
        "algorithm": "Ed25519",
        "key_id": key_id,
        "signature": base64.b64encode(private.sign(canonical)).decode("ascii"),
    }


def _issuance_with_manifest(*, with_manifest=True):
    now = timezone.now()
    suffix = uuid.uuid4().hex[:8]
    org = Organization.objects.create(name="Attestation", slug=f"att-{suffix}")
    actor = User.objects.create_user(
        username=f"issuer-{suffix}",
        password=uuid.uuid4().hex,
        organization=org,
        role=Role.ISSUER,
    )
    upload = UploadRequest.objects.create(
        organization=org,
        requested_by=actor,
        purpose=UploadPurpose.ISSUANCE,
        object_key=f"uploads/orphan/issuance_input/{org.id}/{uuid.uuid4().hex}.bin",
        expected_sha256="a" * 64,
        size_bytes=1,
        expires_at=now + timedelta(minutes=15),
    )
    document = Document.objects.create(
        organization=org,
        created_by=actor,
        upload_request=upload,
        source_object_key=f"inputs/issuance/{org.id}/{upload.id}.bin",
        expected_source_sha256="a" * 64,
    )
    recipient = Recipient.objects.create(
        organization=org, external_reference="R", display_name="Người nhận thử nghiệm"
    )
    issuance = Issuance.objects.create(
        organization=org, document=document, recipient=recipient, created_by=actor
    )
    if not with_manifest:
        return org, issuance, None
    private = Ed25519PrivateKey.generate()
    pem = (
        private.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii")
    )
    key = SigningKey.objects.create(
        organization=org,
        key_id=f"key-{suffix}",
        public_key=pem,
        valid_from=now - timedelta(minutes=5),
        valid_until=now + timedelta(days=1),
    )
    public = {
        "schema_version": 1,
        "issuance_id": str(issuance.id),
        "issued_at": ISSUED_AT,
        "output_sha256": OUTPUT_SHA256,
        "fingerprint_algorithm": "candidate-v1",
        "integrity_algorithm": "integrity-v1",
        "signing_key_id": key.key_id,
    }
    internal = dict(
        public,
        document_id=str(document.id),
        recipient_id=str(recipient.id),
        source_sha256="a" * 64,
        retention_policy_id="retention-v1",
    )
    public_payload, public_envelope = _signed(private, public, key.key_id)
    internal_payload, internal_envelope = _signed(private, internal, key.key_id)
    Manifest.objects.create(
        organization=org,
        issuance=issuance,
        signing_key=key,
        internal_payload=internal_payload,
        internal_signature_envelope=internal_envelope,
        public_payload=public_payload,
        public_signature_envelope=public_envelope,
    )
    return org, issuance, public_payload


@pytest.mark.django_db
def test_attestation_projects_the_signed_public_payload():
    org, issuance, public_payload = _issuance_with_manifest()

    attestation = manifest_attestation(
        organization_id=org.id, issuance_id=issuance.id
    )

    assert attestation == {
        "expected_sha256": OUTPUT_SHA256,
        "manifest_sha256": hashlib.sha256(public_payload.encode("utf-8")).hexdigest(),
        "issued_at": ISSUED_AT,
        "signing_key_id": attestation["signing_key_id"],
        "signing_algorithm": "Ed25519",
        "integrity_algorithm": "integrity-v1",
    }
    assert attestation["signing_key_id"].startswith("key-")


@pytest.mark.django_db
def test_attestation_is_absent_without_a_matched_issuance():
    org, _issuance, _payload = _issuance_with_manifest()

    assert manifest_attestation(organization_id=org.id, issuance_id=None) is None


@pytest.mark.django_db
def test_attestation_is_absent_when_the_issuance_carries_no_manifest():
    org, issuance, _payload = _issuance_with_manifest(with_manifest=False)

    assert (
        manifest_attestation(organization_id=org.id, issuance_id=issuance.id) is None
    )


@pytest.mark.django_db
def test_attestation_refuses_to_cross_the_organization_boundary():
    _org_a, issuance, _payload = _issuance_with_manifest()
    other, _other_issuance, _other_payload = _issuance_with_manifest()

    assert (
        manifest_attestation(organization_id=other.id, issuance_id=issuance.id) is None
    )


@pytest.mark.django_db
def test_attestation_never_exposes_internal_manifest_fields():
    org, issuance, _payload = _issuance_with_manifest()

    attestation = manifest_attestation(
        organization_id=org.id, issuance_id=issuance.id
    )

    for internal_only in ("recipient_id", "document_id", "source_sha256", "retention_policy_id"):
        assert internal_only not in attestation
