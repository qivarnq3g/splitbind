import json
import math
from dataclasses import replace
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from jsonschema import Draft202012Validator, FormatChecker
from nacl.signing import VerifyKey

from splitbind_ref.manifest import (
    InternalManifestV1,
    ManifestSigningKey,
    canonicalize_manifest,
    public_manifest,
    sign_manifest,
    signed_manifest_pair,
)


ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture
def internal_manifest():
    return InternalManifestV1(
        schema_version=1,
        issuance_id="12345678-1234-5678-9234-567812345678",
        document_id="22345678-1234-5678-9234-567812345678",
        recipient_id="32345678-1234-5678-9234-567812345678",
        issued_at="2026-08-29T06:30:00Z",
        source_sha256="11" * 32,
        output_sha256="22" * 32,
        fingerprint_algorithm="splitbind-fingerprint-v1",
        integrity_algorithm="splitbind-integrity-v1",
        signing_key_id="test-ed25519-2026-08",
        retention_policy_id="course-record-v1",
    )


@pytest.fixture
def signing_key():
    return ManifestSigningKey.generate("test-ed25519-2026-08")


def test_rfc8785_canonicalization_has_hand_checked_utf8_bytes():
    value = {"z": 1.0, "a": "€", "nested": {"b": True, "a": None}}

    canonical = canonicalize_manifest(value)

    assert canonical == '{"a":"€","nested":{"a":null,"b":true},"z":1}'.encode()


@pytest.mark.parametrize(
    "value",
    [
        {"value": math.nan},
        {"value": math.inf},
        {"value": b"not-json"},
        {1: "non-string-key"},
        {"value": 2**53},
        '{"duplicate":1,"duplicate":2}',
    ],
)
def test_canonicalization_rejects_ambiguous_or_unsupported_values(value):
    with pytest.raises((TypeError, ValueError), match="manifest"):
        canonicalize_manifest(value)


def test_public_manifest_has_only_the_seven_approved_fields(internal_manifest):
    external = public_manifest(internal_manifest)

    assert external.model_dump() == {
        "schema_version": 1,
        "issuance_id": "12345678-1234-5678-9234-567812345678",
        "issued_at": "2026-08-29T06:30:00Z",
        "output_sha256": "22" * 32,
        "fingerprint_algorithm": "splitbind-fingerprint-v1",
        "integrity_algorithm": "splitbind-integrity-v1",
        "signing_key_id": "test-ed25519-2026-08",
    }
    serialized = canonicalize_manifest(external)
    for forbidden in (
        b"document_id",
        b"recipient_id",
        b"source_sha256",
        b"retention_policy_id",
        b"object_key",
        b"private_key",
    ):
        assert forbidden not in serialized


def test_signature_verifies_with_independent_pynacl_library(
    internal_manifest, signing_key
):
    external = public_manifest(internal_manifest)
    canonical = canonicalize_manifest(external)

    envelope = sign_manifest(canonical, signing_key)
    public_bytes = signing_key.public_key.public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )

    assert envelope.algorithm == "Ed25519"
    assert envelope.key_id == "test-ed25519-2026-08"
    assert VerifyKey(public_bytes).verify(canonical, envelope.signature) == canonical


def test_internal_and_public_payloads_are_canonicalized_and_signed_separately(
    internal_manifest, signing_key
):
    pair = signed_manifest_pair(internal_manifest, signing_key)
    public_bytes = signing_key.public_key.public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    verifier = VerifyKey(public_bytes)

    assert pair.internal.canonical != pair.public.canonical
    assert pair.internal.canonical == canonicalize_manifest(internal_manifest)
    assert pair.public.canonical == canonicalize_manifest(pair.public.manifest)
    assert verifier.verify(
        pair.internal.canonical, pair.internal.envelope.signature
    ) == pair.internal.canonical
    assert verifier.verify(
        pair.public.canonical, pair.public.envelope.signature
    ) == pair.public.canonical
    assert "private" not in repr(pair).lower()


def test_signing_key_id_must_match_manifest_metadata(internal_manifest):
    mismatched = ManifestSigningKey.generate("different-key")

    with pytest.raises(ValueError, match="signing_key_id"):
        signed_manifest_pair(internal_manifest, mismatched)


@pytest.mark.parametrize(
    "issued_at",
    [
        "2026-99-99T99:99:99Z",
        "2026-02-30T12:00:00Z",
        "2026-08-29T24:00:00Z",
        "2026-08-29T06:30:60Z",
    ],
)
def test_manifest_rejects_impossible_rfc3339_utc_timestamp(
    internal_manifest, issued_at
):
    with pytest.raises(ValueError, match="issued_at"):
        replace(internal_manifest, issued_at=issued_at)


@pytest.mark.parametrize(
    ("schema_name", "projection"),
    [
        ("internal-manifest-v1.schema.json", lambda value: value),
        ("public-manifest-v1.schema.json", public_manifest),
    ],
)
def test_manifest_models_match_their_strict_draft_2020_12_schemas(
    schema_name, projection, internal_manifest
):
    schema = json.loads(
        (ROOT / "contracts/jsonschema" / schema_name).read_text(encoding="utf-8")
    )
    manifest = projection(internal_manifest).model_dump()

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(manifest)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["additionalProperties"] is False
