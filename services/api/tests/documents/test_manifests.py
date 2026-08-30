import base64
import json
import uuid
from datetime import timedelta

import pytest
import rfc8785
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key as generate_rsa_private_key
from django.core.exceptions import ValidationError
from django.utils import timezone

from splitbind.access.models import Organization, Recipient, Role, SigningKey, SigningKeyStatus, User
from splitbind.documents.manifests import shareable_public_manifest, verify_stored_manifest
from splitbind.documents.models import Document, Issuance, Manifest
from splitbind.uploads.models import UploadPurpose, UploadRequest


def key_material():
    private = Ed25519PrivateKey.generate()
    public_pem = private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    return private, public_pem


def public_payload(key_id="manifest-key-1"):
    return {
        "schema_version": 1,
        "issuance_id": str(uuid.uuid4()),
        "issued_at": "2026-08-30T00:00:00Z",
        "output_sha256": "a" * 64,
        "fingerprint_algorithm": "candidate-v1",
        "integrity_algorithm": "integrity-v1",
        "signing_key_id": key_id,
    }


def signed(private, payload, key_id="manifest-key-1"):
    canonical = rfc8785.dumps(payload)
    return canonical.decode("utf-8"), {
        "algorithm": "Ed25519",
        "key_id": key_id,
        "signature": base64.b64encode(private.sign(canonical)).decode("ascii"),
    }


@pytest.fixture
def manifest_domain(db):
    org = Organization.objects.create(name="Manifest domain", slug=f"domain-{uuid.uuid4().hex[:8]}")
    actor = User.objects.create_user(username=f"domain-{uuid.uuid4().hex[:8]}", password="test", organization=org, role=Role.ISSUER)
    upload = UploadRequest.objects.create(
        organization=org, requested_by=actor, purpose=UploadPurpose.ISSUANCE,
        object_key=f"uploads/orphan/issuance_input/{org.id}/{uuid.uuid4().hex}.bin",
        expected_sha256="a" * 64, size_bytes=1,
        expires_at=timezone.now() + timedelta(minutes=15),
    )
    document = Document.objects.create(
        organization=org, created_by=actor, upload_request=upload,
        source_object_key=f"inputs/issuance/{org.id}/{upload.id}.bin",
        expected_source_sha256="a" * 64,
    )
    recipient = Recipient.objects.create(
        organization=org, external_reference="R", display_name="Synthetic",
    )
    issuance = Issuance.objects.create(
        organization=org, document=document, recipient=recipient, created_by=actor,
    )
    return org, issuance


@pytest.mark.django_db
def test_exact_canonical_public_manifest_verifies_and_is_trusted_in_window():
    private, pem = key_material()
    now = timezone.now()
    org = Organization.objects.create(name="Manifest", slug=f"manifest-{uuid.uuid4().hex[:8]}")
    key = SigningKey.objects.create(
        organization=org,
        key_id="manifest-key-1",
        public_key=pem,
        valid_from=now - timedelta(minutes=1),
        valid_until=now + timedelta(minutes=1),
    )
    payload, envelope = signed(private, public_payload())

    result = verify_stored_manifest(payload, envelope, key, now=now)

    assert result.cryptographically_valid is True
    assert result.trusted is True
    assert result.lifecycle == "active"
    assert result.code == "VALID_TRUSTED"
    assert set(result.as_public_dict()) == {"cryptographically_valid", "trusted", "lifecycle", "code"}


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("noncanonical", "NONCANONICAL_PAYLOAD"),
        ("duplicate", "INVALID_PAYLOAD"),
        ("tamper", "INVALID_SIGNATURE"),
        ("extra_envelope", "INVALID_ENVELOPE"),
        ("bad_base64", "INVALID_ENVELOPE"),
        ("key_mismatch", "KEY_ID_MISMATCH"),
    ],
)
def test_manifest_verification_fails_closed_without_leaking_payload(mutation, expected_code):
    private, pem = key_material()
    now = timezone.now()
    org = Organization.objects.create(name="Manifest", slug=f"manifest-{uuid.uuid4().hex[:8]}")
    key = SigningKey.objects.create(
        organization=org, key_id="manifest-key-1", public_key=pem,
        valid_from=now - timedelta(minutes=1),
    )
    payload_object = public_payload()
    payload, envelope = signed(private, payload_object)
    if mutation == "noncanonical":
        payload = json.dumps(payload_object, indent=2)
    elif mutation == "duplicate":
        payload = payload[:-1] + ',"schema_version":1}'
    elif mutation == "tamper":
        payload_object["output_sha256"] = "b" * 64
        payload = rfc8785.dumps(payload_object).decode()
    elif mutation == "extra_envelope":
        envelope["recipient_id"] = "private"
    elif mutation == "bad_base64":
        envelope["signature"] = "not base64!"
    elif mutation == "key_mismatch":
        envelope["key_id"] = "other-key"

    result = verify_stored_manifest(payload, envelope, key, now=now)

    assert result.trusted is False
    assert result.code == expected_code
    serialized = json.dumps(result.as_public_dict()).lower()
    assert "recipient" not in serialized and "document" not in serialized and "object_key" not in serialized


@pytest.mark.django_db
def test_revoked_key_preserves_crypto_match_but_never_establishes_trust():
    private, pem = key_material()
    now = timezone.now()
    org = Organization.objects.create(name="Revoked", slug=f"revoked-{uuid.uuid4().hex[:8]}")
    key = SigningKey.objects.create(
        organization=org, key_id="manifest-key-1", public_key=pem,
        status=SigningKeyStatus.REVOKED,
        valid_from=now - timedelta(days=2), revoked_at=now - timedelta(days=1),
    )
    payload, envelope = signed(private, public_payload())

    result = verify_stored_manifest(payload, envelope, key, now=now)

    assert result.cryptographically_valid is True
    assert result.trusted is False
    assert result.lifecycle == "revoked"
    assert result.code == "VALID_REVOKED"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("status", "inside", "trusted"),
    [
        (SigningKeyStatus.VERIFY_ONLY, True, True),
        (SigningKeyStatus.ACTIVE, False, False),
    ],
)
def test_verify_only_and_validity_window_are_distinct_trust_inputs(status, inside, trusted):
    private, pem = key_material()
    now = timezone.now()
    org = Organization.objects.create(name="Lifecycle", slug=f"lifecycle-{uuid.uuid4().hex[:8]}")
    key = SigningKey.objects.create(
        organization=org,
        key_id="manifest-key-1",
        public_key=pem,
        status=status,
        valid_from=now - timedelta(minutes=2) if inside else now + timedelta(minutes=1),
        valid_until=now + timedelta(minutes=2) if inside else now + timedelta(minutes=3),
    )
    payload, envelope = signed(private, public_payload())

    result = verify_stored_manifest(payload, envelope, key, now=now)

    assert result.cryptographically_valid is True
    assert result.trusted is trusted
    assert result.code == ("VALID_TRUSTED" if trusted else "VALID_UNTRUSTED_WINDOW")


@pytest.mark.django_db
def test_signing_key_normal_writes_accept_only_ed25519_spki_public_pem():
    private, pem = key_material()
    org = Organization.objects.create(name="Keys", slug=f"keys-{uuid.uuid4().hex[:8]}")
    now = timezone.now()
    valid = SigningKey.objects.create(
        organization=org, key_id="valid-key", public_key=pem, valid_from=now,
    )
    assert valid.algorithm == "Ed25519"

    private_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    with pytest.raises(ValidationError):
        SigningKey.objects.create(
            organization=org, key_id="private-key", public_key=private_pem, valid_from=now,
        )
    with pytest.raises(ValidationError):
        SigningKey.objects.create(
            organization=org, key_id="bad-window", public_key=pem,
            valid_from=now, valid_until=now - timedelta(seconds=1),
        )
    with pytest.raises(ValidationError):
        SigningKey.objects.create(
            organization=org, key_id="unsafe-meta", public_key=pem,
            valid_from=now, metadata={"private_key": "forbidden"},
        )
    rsa_pem = generate_rsa_private_key(public_exponent=65537, key_size=2048).public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    with pytest.raises(ValidationError):
        SigningKey.objects.create(
            organization=org, key_id="rsa-key", public_key=rsa_pem, valid_from=now,
        )


@pytest.mark.django_db
def test_manifest_payload_size_is_bounded_before_parsing():
    private, pem = key_material()
    now = timezone.now()
    org = Organization.objects.create(name="Size", slug=f"size-{uuid.uuid4().hex[:8]}")
    key = SigningKey.objects.create(
        organization=org, key_id="manifest-key-1", public_key=pem, valid_from=now,
    )

    result = verify_stored_manifest(" " * (1024 * 1024 + 1), {}, key, now=now)

    assert result.code == "INVALID_PAYLOAD"
    assert result.cryptographically_valid is False


@pytest.mark.django_db
def test_signature_base64_must_be_the_exact_canonical_88_character_encoding():
    private, pem = key_material()
    now = timezone.now()
    org = Organization.objects.create(name="Canonical", slug=f"canonical-{uuid.uuid4().hex[:8]}")
    key = SigningKey.objects.create(
        organization=org, key_id="manifest-key-1", public_key=pem,
        valid_from=now - timedelta(minutes=1),
    )
    payload, envelope = signed(private, public_payload())
    envelope["signature"] = envelope["signature"] + "="

    assert verify_stored_manifest(payload, envelope, key, now=now).code == "INVALID_ENVELOPE"


@pytest.mark.django_db
def test_registry_algorithm_is_required_for_verification_and_readiness(monkeypatch):
    private, pem = key_material()
    now = timezone.now()
    org = Organization.objects.create(name="Algorithm", slug=f"algorithm-{uuid.uuid4().hex[:8]}")
    key = SigningKey.objects.create(
        organization=org, key_id="manifest-key-1", public_key=pem,
        valid_from=now - timedelta(minutes=1),
    )
    from django.db import connection
    with connection.cursor() as cursor:
        cursor.execute("UPDATE access_signingkey SET algorithm = %s WHERE id = %s", ["RSA", key.id.hex])
    key.refresh_from_db()
    payload, envelope = signed(private, public_payload())

    assert verify_stored_manifest(payload, envelope, key, now=now).code == "INVALID_REGISTRY"
    from splitbind.health.readiness import public_key_registry_ready
    assert public_key_registry_ready() is False


@pytest.mark.django_db
def test_signing_key_history_is_immutable_except_validated_lifecycle_transition():
    _, pem = key_material()
    now = timezone.now()
    org = Organization.objects.create(name="Immutable", slug=f"immutable-{uuid.uuid4().hex[:8]}")
    key = SigningKey.objects.create(
        organization=org, key_id="history-key", public_key=pem, valid_from=now,
        metadata={"label": "historical"},
    )

    key.key_id = "replacement"
    with pytest.raises(ValidationError, match="immutable"):
        key.save(update_fields=["key_id"])
    with pytest.raises(ValidationError, match="immutable"):
        SigningKey._base_manager.filter(pk=key.pk).update(metadata={"label": "changed"})
    with pytest.raises(ValidationError, match="preserved"):
        key.delete()

    from splitbind.access.services import transition_signing_key
    transitioned = transition_signing_key(key.pk, SigningKeyStatus.VERIFY_ONLY, at=now + timedelta(seconds=1))
    assert transitioned.status == SigningKeyStatus.VERIFY_ONLY
    revoked = transition_signing_key(key.pk, SigningKeyStatus.REVOKED, at=now + timedelta(seconds=2))
    assert revoked.revoked_at == now + timedelta(seconds=2)
    with pytest.raises(ValidationError, match="terminal"):
        transition_signing_key(key.pk, SigningKeyStatus.ACTIVE, at=now + timedelta(seconds=3))


@pytest.mark.django_db
def test_manifest_history_cannot_be_updated_or_deleted(manifest_domain):
    organization, issuance = manifest_domain
    _, pem = key_material()
    signing_key = SigningKey.objects.create(
        organization=organization, key_id="immutable-manifest-key", public_key=pem,
        valid_from=timezone.now(),
    )
    record = Manifest.objects.create(
        organization=organization, issuance=issuance, signing_key=signing_key,
        internal_payload="{}", internal_signature_envelope={},
        public_payload="{}", public_signature_envelope={},
    )
    record.public_payload = '{"changed":true}'
    with pytest.raises(ValidationError, match="immutable"):
        record.save(update_fields=["public_payload"])
    with pytest.raises(ValidationError, match="immutable"):
        Manifest._base_manager.filter(pk=record.pk).update(public_payload="{}")
    with pytest.raises(ValidationError, match="preserved"):
        record.delete()


@pytest.mark.django_db
def test_shareable_public_manifest_requires_trusted_public_projection(manifest_domain):
    organization, issuance = manifest_domain
    private, pem = key_material()
    now = timezone.now()
    key = SigningKey.objects.create(
        organization=organization, key_id="manifest-key-1", public_key=pem,
        valid_from=now - timedelta(minutes=1), valid_until=now + timedelta(minutes=1),
    )
    public, public_envelope = signed(private, public_payload())
    internal_object = {**public_payload(), "document_id": str(uuid.uuid4()),
                       "recipient_id": str(uuid.uuid4()), "source_sha256": "b" * 64,
                       "retention_policy_id": "retention-v1"}
    internal, internal_envelope = signed(private, internal_object)
    record = Manifest.objects.create(
        organization=organization, issuance=issuance, signing_key=key,
        internal_payload=internal, internal_signature_envelope=internal_envelope,
        public_payload=public, public_signature_envelope=public_envelope,
    )

    projected = shareable_public_manifest(record, now=now)
    assert projected["payload"] == public
    assert "recipient_id" not in str(projected) and "document_id" not in str(projected)

    Manifest._base_manager.model.objects  # keep the supported manager visible to the test
    record.public_payload = internal
    record.public_signature_envelope = internal_envelope
    with pytest.raises(ValidationError, match="shareable"):
        shareable_public_manifest(record, now=now)
