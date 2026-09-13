import base64
import json
import uuid
from datetime import timedelta

import pytest
import rfc8785
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from django.core.cache import cache
from django.test import Client
from django.utils import timezone

from splitbind.access.models import (
    Organization,
    Recipient,
    Role,
    SigningKey,
    SigningKeyStatus,
    User,
)
from splitbind.access.services import transition_signing_key
from splitbind.audit.models import AuditEvent, AuditOutcome
from splitbind.documents.models import Document, Issuance, Manifest
from splitbind.uploads.models import UploadPurpose, UploadRequest


INTERNAL_ONLY = ("recipient_id", "document_id", "source_sha256", "retention_policy_id")


def throwaway_credential():
    return uuid.uuid4().hex


def key_material():
    private = Ed25519PrivateKey.generate()
    public_pem = (
        private.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii")
    )
    return private, public_pem


def signed(private, payload, key_id):
    canonical = rfc8785.dumps(payload)
    return canonical.decode("utf-8"), {
        "algorithm": "Ed25519",
        "key_id": key_id,
        "signature": base64.b64encode(private.sign(canonical)).decode("ascii"),
    }


@pytest.fixture
def issued(db):
    cache.clear()
    now = timezone.now()
    suffix = uuid.uuid4().hex[:8]
    org = Organization.objects.create(name="Manifest api", slug=f"api-{suffix}")
    secret = throwaway_credential()
    actor = User.objects.create_user(
        username=f"issuer-{suffix}",
        password=secret,
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
        organization=org,
        external_reference="R",
        display_name="Người nhận thử nghiệm",
    )
    issuance = Issuance.objects.create(
        organization=org,
        document=document,
        recipient=recipient,
        created_by=actor,
    )
    private, pem = key_material()
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
        "issued_at": "2026-08-30T00:00:00Z",
        "output_sha256": "b" * 64,
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
    public_payload, public_envelope = signed(private, public, key.key_id)
    internal_payload, internal_envelope = signed(private, internal, key.key_id)
    Manifest.objects.create(
        organization=org,
        issuance=issuance,
        signing_key=key,
        internal_payload=internal_payload,
        internal_signature_envelope=internal_envelope,
        public_payload=public_payload,
        public_signature_envelope=public_envelope,
    )
    return org, actor, secret, issuance, recipient


def sign_in(actor, secret):
    client = Client()
    assert client.login(username=actor.username, password=secret)
    return client


@pytest.mark.django_db
def test_manifest_endpoint_returns_a_signature_a_third_party_can_check(issued):
    _, actor, secret, issuance, _ = issued

    response = sign_in(actor, secret).get(f"/api/v1/issuances/{issuance.id}/manifest")

    assert response.status_code == 200
    body = response.json()

    payload = body["payload"].encode("utf-8")
    signature = base64.b64decode(body["signature"]["signature"])
    public_key = serialization.load_pem_public_key(
        body["public_key"]["public_key"].encode("ascii")
    )
    assert isinstance(public_key, Ed25519PublicKey)
    public_key.verify(signature, payload)

    assert json.loads(body["payload"])["issuance_id"] == str(issuance.id)
    assert body["public_key"]["algorithm"] == "Ed25519"


@pytest.mark.django_db
def test_manifest_endpoint_never_discloses_the_recipient(issued):
    _, actor, secret, issuance, recipient = issued

    response = sign_in(actor, secret).get(f"/api/v1/issuances/{issuance.id}/manifest")

    assert response.status_code == 200
    serialized = json.dumps(response.json())
    assert str(recipient.id) not in serialized
    assert recipient.display_name not in serialized
    for field in INTERNAL_ONLY:
        assert field not in json.loads(response.json()["payload"])


@pytest.mark.django_db
def test_manifest_endpoint_hides_another_organization_behind_a_404(issued):
    _, _, _, issuance, _ = issued
    suffix = uuid.uuid4().hex[:8]
    other_org = Organization.objects.create(name="Other", slug=f"other-{suffix}")
    outsider_secret = throwaway_credential()
    outsider = User.objects.create_user(
        username=f"outsider-{suffix}",
        password=outsider_secret,
        organization=other_org,
        role=Role.ISSUER,
    )

    response = sign_in(outsider, outsider_secret).get(f"/api/v1/issuances/{issuance.id}/manifest")

    assert response.status_code == 404
    assert AuditEvent.objects.filter(
        action="issuance.manifest_denied", outcome=AuditOutcome.DENIED
    ).exists()


@pytest.mark.django_db
def test_manifest_endpoint_requires_authentication(issued):
    _, _, _, issuance, _ = issued

    response = Client().get(f"/api/v1/issuances/{issuance.id}/manifest")

    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_manifest_endpoint_reports_a_conflict_when_no_manifest_exists(issued):
    org, actor, secret, _, _ = issued
    upload = UploadRequest.objects.create(
        organization=org,
        requested_by=actor,
        purpose=UploadPurpose.ISSUANCE,
        object_key=f"uploads/orphan/issuance_input/{org.id}/{uuid.uuid4().hex}.bin",
        expected_sha256="c" * 64,
        size_bytes=1,
        expires_at=timezone.now() + timedelta(minutes=15),
    )
    document = Document.objects.create(
        organization=org,
        created_by=actor,
        upload_request=upload,
        source_object_key=f"inputs/issuance/{org.id}/{upload.id}.bin",
        expected_source_sha256="c" * 64,
    )
    bare = Issuance.objects.create(
        organization=org,
        document=document,
        recipient=Recipient.objects.filter(organization=org).first(),
        created_by=actor,
    )

    response = sign_in(actor, secret).get(f"/api/v1/issuances/{bare.id}/manifest")

    assert response.status_code == 409
    assert response.json()["code"] == "MANIFEST_UNAVAILABLE"


@pytest.mark.django_db
def test_manifest_endpoint_refuses_to_share_a_revoked_key(issued):
    _, actor, secret, issuance, _ = issued
    key = SigningKey.objects.get(manifests__issuance=issuance)
    transition_signing_key(key.pk, SigningKeyStatus.REVOKED, at=timezone.now())

    response = sign_in(actor, secret).get(f"/api/v1/issuances/{issuance.id}/manifest")

    assert response.status_code == 409
    assert response.json()["code"] == "MANIFEST_NOT_SHAREABLE"
