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

from splitbind.access.models import Organization, SigningKey, SigningKeyStatus
from splitbind.documents.manifests import verify_stored_manifest


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
