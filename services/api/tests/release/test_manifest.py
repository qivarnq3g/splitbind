import base64
import json
from datetime import datetime, timezone
from io import StringIO
from uuid import UUID

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.core.management import call_command
from django.core.management.base import CommandError

from splitbind.access.models import Organization, SigningKey
from splitbind.documents.manifests import verify_stored_manifest
from splitbind.release.manifest import build_signed_issuance_manifest


ISSUED_AT = datetime(2026, 9, 7, 4, 5, 6, tzinfo=timezone.utc)
ISSUANCE_ID = UUID("00112233-4455-4677-8899-aabbccddeeff")
DOCUMENT_ID = UUID("11112233-4455-4677-8899-aabbccddeeff")
RECIPIENT_ID = UUID("22222233-4455-4677-8899-aabbccddeeff")
SOURCE_SHA256 = "11" * 32
OUTPUT_SHA256 = "22" * 32


def _private_pem(private_key):
    return private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


@pytest.mark.django_db
def test_signed_manifest_pair_verifies_exact_public_and_internal_payloads():
    private_key = Ed25519PrivateKey.generate()
    organization = Organization.objects.create(name="Manifest test", slug="manifest-test")
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")
    key = SigningKey.objects.create(
        organization=organization,
        key_id="integrity-key-1",
        public_key=public_pem,
        valid_from=ISSUED_AT,
    )

    pair = build_signed_issuance_manifest(
        issuance_id=ISSUANCE_ID,
        document_id=DOCUMENT_ID,
        recipient_id=RECIPIENT_ID,
        issued_at=ISSUED_AT,
        source_sha256=SOURCE_SHA256,
        output_sha256=OUTPUT_SHA256,
        signing_key_id=key.key_id,
        private_key=private_key,
        retention_policy_id="retention-v1",
    )

    public = verify_stored_manifest(
        pair.public_payload,
        pair.public_signature_envelope,
        key,
        now=ISSUED_AT,
        expected_kind="public",
    )
    internal = verify_stored_manifest(
        pair.internal_payload,
        pair.internal_signature_envelope,
        key,
        now=ISSUED_AT,
        expected_kind="internal",
    )
    assert public.trusted is True
    assert internal.trusted is True
    assert "recipient_id" not in json.loads(pair.public_payload)
    assert pair.public_payload != pair.internal_payload
    assert pair.public_signature_envelope != pair.internal_signature_envelope


@pytest.mark.django_db
def test_modified_output_hash_signature_or_key_id_fails_closed():
    private_key = Ed25519PrivateKey.generate()
    organization = Organization.objects.create(name="Manifest mutation", slug="manifest-mutation")
    key = SigningKey.objects.create(
        organization=organization,
        key_id="integrity-key-1",
        public_key=private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("ascii"),
        valid_from=ISSUED_AT,
    )
    pair = build_signed_issuance_manifest(
        issuance_id=ISSUANCE_ID,
        document_id=DOCUMENT_ID,
        recipient_id=RECIPIENT_ID,
        issued_at=ISSUED_AT,
        source_sha256=SOURCE_SHA256,
        output_sha256=OUTPUT_SHA256,
        signing_key_id=key.key_id,
        private_key=private_key,
        retention_policy_id="retention-v1",
    )

    changed_payload = pair.public_payload.replace(OUTPUT_SHA256, "33" * 32)
    changed_signature = dict(pair.public_signature_envelope)
    signature_bytes = bytearray(base64.b64decode(changed_signature["signature"]))
    signature_bytes[0] ^= 1
    changed_signature["signature"] = base64.b64encode(signature_bytes).decode("ascii")
    changed_key_id = dict(pair.public_signature_envelope, key_id="other-key")

    assert not verify_stored_manifest(changed_payload, pair.public_signature_envelope, key).trusted
    assert not verify_stored_manifest(pair.public_payload, changed_signature, key).trusted
    assert not verify_stored_manifest(pair.public_payload, changed_key_id, key).trusted


@pytest.mark.django_db
def test_registration_command_is_idempotent_but_rejects_changed_key_bytes(tmp_path):
    organization = Organization.objects.create(name="Registry", slug="registry")
    key_file = tmp_path / "manifest-signing-key.pem"
    key_file.write_bytes(_private_pem(Ed25519PrivateKey.generate()))

    arguments = {
        "organization_id": str(organization.id),
        "key_id": "integrity-key-1",
        "private_key_file": str(key_file),
        "valid_from": "2026-09-07T04:05:06Z",
        "stdout": StringIO(),
    }
    call_command("register_integrity_signing_key", **arguments)
    call_command("register_integrity_signing_key", **arguments)
    original_public_key = SigningKey.objects.get(key_id="integrity-key-1").public_key

    key_file.write_bytes(_private_pem(Ed25519PrivateKey.generate()))
    with pytest.raises(CommandError, match="different public key"):
        call_command("register_integrity_signing_key", **arguments)

    assert SigningKey.objects.count() == 1
    assert SigningKey.objects.get(key_id="integrity-key-1").public_key == original_public_key
