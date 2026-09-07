from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import rfc8785
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


@dataclass(frozen=True, slots=True)
class SignedIssuanceManifest:
    internal_payload: str
    internal_signature_envelope: dict[str, str]
    public_payload: str
    public_signature_envelope: dict[str, str]


def load_manifest_signing_key(path: str | Path) -> Ed25519PrivateKey:
    key_path = Path(path)
    try:
        encoded = key_path.read_bytes()
        private_key = serialization.load_pem_private_key(encoded, password=None)
    except (OSError, TypeError, ValueError) as error:
        raise ValueError("manifest signing key file is invalid") from error
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ValueError("manifest signing key must be Ed25519")
    return private_key


def public_key_pem(private_key: Ed25519PrivateKey) -> str:
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError("private_key must be an Ed25519 private key")
    return private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")


def build_signed_issuance_manifest(
    *,
    issuance_id: UUID,
    document_id: UUID,
    recipient_id: UUID,
    issued_at: datetime,
    source_sha256: str,
    output_sha256: str,
    signing_key_id: str,
    private_key: Ed25519PrivateKey,
    retention_policy_id: str,
) -> SignedIssuanceManifest:
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TypeError("private_key must be an Ed25519 private key")
    if issued_at.tzinfo is None or issued_at.utcoffset() is None:
        raise ValueError("issued_at must be timezone-aware")
    timestamp = issued_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    internal = {
        "schema_version": 1,
        "issuance_id": str(issuance_id),
        "document_id": str(document_id),
        "recipient_id": str(recipient_id),
        "issued_at": timestamp,
        "source_sha256": source_sha256,
        "output_sha256": output_sha256,
        "fingerprint_algorithm": "none",
        "integrity_algorithm": "integrity_release_v1",
        "signing_key_id": signing_key_id,
        "retention_policy_id": retention_policy_id,
    }
    public = {
        key: internal[key]
        for key in (
            "schema_version",
            "issuance_id",
            "issued_at",
            "output_sha256",
            "fingerprint_algorithm",
            "integrity_algorithm",
            "signing_key_id",
        )
    }
    internal_bytes = rfc8785.dumps(internal)
    public_bytes = rfc8785.dumps(public)
    return SignedIssuanceManifest(
        internal_payload=internal_bytes.decode("utf-8"),
        internal_signature_envelope=_sign(internal_bytes, signing_key_id, private_key),
        public_payload=public_bytes.decode("utf-8"),
        public_signature_envelope=_sign(public_bytes, signing_key_id, private_key),
    )


def _sign(
    canonical: bytes,
    key_id: str,
    private_key: Ed25519PrivateKey,
) -> dict[str, str]:
    return {
        "algorithm": "Ed25519",
        "key_id": key_id,
        "signature": base64.b64encode(private_key.sign(canonical)).decode("ascii"),
    }
