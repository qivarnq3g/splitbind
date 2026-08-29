"""Strict RFC 8785 manifests and detached Ed25519 signatures."""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping
from uuid import UUID

import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ALGORITHM = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
_MAX_SAFE_INTEGER = 9_007_199_254_740_991
_MAX_CANONICAL_BYTES = 1_048_576


@dataclass(frozen=True, slots=True)
class InternalManifestV1:
    schema_version: int
    issuance_id: str
    document_id: str
    recipient_id: str
    issued_at: str
    source_sha256: str
    output_sha256: str
    fingerprint_algorithm: str
    integrity_algorithm: str
    signing_key_id: str
    retention_policy_id: str

    def __post_init__(self) -> None:
        _validate_internal(self.model_dump())

    def model_dump(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PublicManifestV1:
    schema_version: int
    issuance_id: str
    issued_at: str
    output_sha256: str
    fingerprint_algorithm: str
    integrity_algorithm: str
    signing_key_id: str

    def __post_init__(self) -> None:
        _validate_public(self.model_dump())

    def model_dump(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ManifestSigningKey:
    key_id: str
    _private_key: Ed25519PrivateKey = field(repr=False)

    def __post_init__(self) -> None:
        _validate_bounded_string("key_id", self.key_id)
        if not isinstance(self._private_key, Ed25519PrivateKey):
            raise TypeError("private signing key must be an Ed25519PrivateKey")

    @classmethod
    def generate(cls, key_id: str) -> "ManifestSigningKey":
        return cls(key_id=key_id, _private_key=Ed25519PrivateKey.generate())

    @property
    def public_key(self) -> Ed25519PublicKey:
        return self._private_key.public_key()

    def sign(self, canonical: bytes) -> bytes:
        return self._private_key.sign(canonical)


@dataclass(frozen=True, slots=True)
class SignatureEnvelope:
    algorithm: str
    key_id: str
    signature: bytes


@dataclass(frozen=True, slots=True)
class SignedManifest:
    manifest: InternalManifestV1 | PublicManifestV1
    canonical: bytes
    envelope: SignatureEnvelope


@dataclass(frozen=True, slots=True)
class SignedManifestPair:
    internal: SignedManifest
    public: SignedManifest


def canonicalize_manifest(manifest: object) -> bytes:
    """Return JCS bytes after rejecting non-I-JSON and ambiguous input."""

    value = _plain_manifest(manifest)
    _validate_json_value(value)
    try:
        canonical = rfc8785.dumps(value)
    except (rfc8785.CanonicalizationError, UnicodeError, ValueError, TypeError) as error:
        raise ValueError("manifest cannot be canonicalized as RFC 8785 JCS") from error
    if len(canonical) > _MAX_CANONICAL_BYTES:
        raise ValueError("manifest canonical payload exceeds 1 MiB")
    return canonical


def sign_manifest(canonical: bytes, private_key: ManifestSigningKey) -> SignatureEnvelope:
    """Sign the exact supplied canonical bytes with Ed25519."""

    if not isinstance(canonical, bytes) or not canonical:
        raise TypeError("canonical manifest must be non-empty bytes")
    if len(canonical) > _MAX_CANONICAL_BYTES:
        raise ValueError("canonical manifest exceeds 1 MiB")
    if not isinstance(private_key, ManifestSigningKey):
        raise TypeError("private_key must be a ManifestSigningKey")
    return SignatureEnvelope(
        algorithm="Ed25519",
        key_id=private_key.key_id,
        signature=private_key.sign(canonical),
    )


def public_manifest(
    internal: InternalManifestV1 | Mapping[str, object],
) -> PublicManifestV1:
    """Project the protected internal record to exactly seven public fields."""

    value = _coerce_internal(internal)
    return PublicManifestV1(
        schema_version=value.schema_version,
        issuance_id=value.issuance_id,
        issued_at=value.issued_at,
        output_sha256=value.output_sha256,
        fingerprint_algorithm=value.fingerprint_algorithm,
        integrity_algorithm=value.integrity_algorithm,
        signing_key_id=value.signing_key_id,
    )


def signed_manifest_pair(
    internal: InternalManifestV1 | Mapping[str, object],
    private_key: ManifestSigningKey,
) -> SignedManifestPair:
    """Canonicalize and sign internal and public payloads independently."""

    value = _coerce_internal(internal)
    if not isinstance(private_key, ManifestSigningKey):
        raise TypeError("private_key must be a ManifestSigningKey")
    if value.signing_key_id != private_key.key_id:
        raise ValueError("manifest signing_key_id does not match the signing key")
    external = public_manifest(value)
    internal_bytes = canonicalize_manifest(value)
    public_bytes = canonicalize_manifest(external)
    return SignedManifestPair(
        internal=SignedManifest(
            manifest=value,
            canonical=internal_bytes,
            envelope=sign_manifest(internal_bytes, private_key),
        ),
        public=SignedManifest(
            manifest=external,
            canonical=public_bytes,
            envelope=sign_manifest(public_bytes, private_key),
        ),
    )


def _plain_manifest(manifest: object) -> object:
    if isinstance(manifest, (InternalManifestV1, PublicManifestV1)):
        return manifest.model_dump()
    if isinstance(manifest, str):
        try:
            return json.loads(
                manifest,
                object_pairs_hook=_unique_object,
                parse_constant=lambda value: (_raise_invalid_constant(value)),
            )
        except (json.JSONDecodeError, ValueError) as error:
            raise ValueError("manifest JSON is invalid or ambiguous") from error
    return manifest


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate manifest member: {key}")
        result[key] = value
    return result


def _raise_invalid_constant(value: str) -> None:
    raise ValueError(f"non-finite manifest number: {value}")


def _validate_json_value(value: object, path: str = "$") -> None:
    if value is None or type(value) in (bool, str):
        return
    if type(value) is int:
        if abs(value) > _MAX_SAFE_INTEGER:
            raise ValueError(f"manifest integer at {path} exceeds the I-JSON safe range")
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError(f"manifest number at {path} must be finite")
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _validate_json_value(item, f"{path}[{index}]")
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise TypeError(f"manifest member name at {path} must be a string")
            _validate_json_value(item, f"{path}.{key}")
        return
    raise TypeError(f"manifest value at {path} is not JSON-compatible")


def _coerce_internal(
    value: InternalManifestV1 | Mapping[str, object],
) -> InternalManifestV1:
    if isinstance(value, InternalManifestV1):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("internal manifest must be InternalManifestV1 or a mapping")
    try:
        return InternalManifestV1(**dict(value))  # type: ignore[arg-type]
    except TypeError as error:
        raise ValueError("internal manifest fields do not match version 1") from error


def _validate_internal(value: Mapping[str, object]) -> None:
    expected = {
        "schema_version", "issuance_id", "document_id", "recipient_id", "issued_at",
        "source_sha256", "output_sha256", "fingerprint_algorithm", "integrity_algorithm",
        "signing_key_id", "retention_policy_id",
    }
    if set(value) != expected:
        raise ValueError("internal manifest fields do not match version 1")
    _validate_common(value)
    _validate_uuid("document_id", value["document_id"])
    _validate_uuid("recipient_id", value["recipient_id"])
    _validate_hash("source_sha256", value["source_sha256"])
    _validate_bounded_string("retention_policy_id", value["retention_policy_id"])


def _validate_public(value: Mapping[str, object]) -> None:
    expected = {
        "schema_version", "issuance_id", "issued_at", "output_sha256",
        "fingerprint_algorithm", "integrity_algorithm", "signing_key_id",
    }
    if set(value) != expected:
        raise ValueError("public manifest fields do not match version 1")
    _validate_common(value)


def _validate_common(value: Mapping[str, object]) -> None:
    if value["schema_version"] != 1 or type(value["schema_version"]) is not int:
        raise ValueError("manifest schema_version must be integer 1")
    _validate_uuid("issuance_id", value["issuance_id"])
    issued_at = value["issued_at"]
    if not isinstance(issued_at, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z", issued_at
    ):
        raise ValueError("manifest issued_at must be an RFC 3339 UTC timestamp")
    _validate_hash("output_sha256", value["output_sha256"])
    for name in ("fingerprint_algorithm", "integrity_algorithm"):
        algorithm = value[name]
        if not isinstance(algorithm, str) or _ALGORITHM.fullmatch(algorithm) is None:
            raise ValueError(f"manifest {name} is invalid")
    _validate_bounded_string("signing_key_id", value["signing_key_id"])


def _validate_uuid(name: str, value: object) -> None:
    if not isinstance(value, str):
        raise TypeError(f"manifest {name} must be a UUID string")
    try:
        parsed = UUID(value)
    except ValueError as error:
        raise ValueError(f"manifest {name} must be a UUID string") from error
    if str(parsed) != value.lower():
        raise ValueError(f"manifest {name} must use canonical UUID text")


def _validate_hash(name: str, value: object) -> None:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"manifest {name} must be lowercase SHA-256 hex")


def _validate_bounded_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not 1 <= len(value) <= 128:
        raise ValueError(f"manifest {name} must contain 1 to 128 characters")
