from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime, timezone as datetime_timezone
from pathlib import Path
from typing import Mapping

import rfc8785
from cryptography.exceptions import InvalidSignature
from django.core.exceptions import ValidationError
from jsonschema import Draft202012Validator, FormatChecker

from splitbind.access.models import SigningKeyStatus, validate_ed25519_public_pem


MAX_MANIFEST_BYTES = 1024 * 1024
_CONTRACT_ROOT = Path(__file__).resolve().parents[4] / "contracts" / "jsonschema"
_SCHEMAS = {
    "public": _CONTRACT_ROOT / "public-manifest-v1.schema.json",
    "internal": _CONTRACT_ROOT / "internal-manifest-v1.schema.json",
}


@dataclass(frozen=True, slots=True)
class ManifestVerification:
    cryptographically_valid: bool
    trusted: bool
    lifecycle: str
    code: str

    def as_public_dict(self) -> dict[str, object]:
        return {
            "cryptographically_valid": self.cryptographically_valid,
            "trusted": self.trusted,
            "lifecycle": self.lifecycle,
            "code": self.code,
        }


def _result(code: str, *, crypto=False, trusted=False, lifecycle="invalid"):
    return ManifestVerification(crypto, trusted, lifecycle, code)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON member")
        result[key] = value
    return result


def _load_schema(kind: str) -> Mapping[str, object]:
    with _SCHEMAS[kind].open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _parse_exact_payload(payload: object):
    if not isinstance(payload, str):
        raise ValueError("payload must be stored text")
    encoded = payload.encode("utf-8")
    if not encoded or len(encoded) > MAX_MANIFEST_BYTES:
        raise ValueError("payload size is invalid")
    value = json.loads(
        payload,
        object_pairs_hook=_unique_object,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite JSON")),
    )
    if not isinstance(value, dict):
        raise ValueError("payload must be an object")
    canonical = rfc8785.dumps(value)
    return value, encoded, canonical


def verify_stored_manifest(manifest, signature, public_key, *, now=None) -> ManifestVerification:
    """Verify stored canonical bytes with one public registry record; never signs."""
    lifecycle = getattr(public_key, "status", "invalid")
    try:
        value, stored, canonical = _parse_exact_payload(manifest)
    except Exception:
        return _result("INVALID_PAYLOAD", lifecycle=lifecycle)
    if stored != canonical:
        return _result("NONCANONICAL_PAYLOAD", lifecycle=lifecycle)
    kind = "internal" if "recipient_id" in value else "public"
    try:
        Draft202012Validator(
            _load_schema(kind), format_checker=FormatChecker()
        ).validate(value)
    except Exception:
        return _result("INVALID_SCHEMA", lifecycle=lifecycle)
    if not isinstance(signature, dict) or set(signature) != {"algorithm", "key_id", "signature"}:
        return _result("INVALID_ENVELOPE", lifecycle=lifecycle)
    if signature.get("algorithm") != "Ed25519":
        return _result("INVALID_ENVELOPE", lifecycle=lifecycle)
    envelope_key_id = signature.get("key_id")
    if (
        not isinstance(envelope_key_id, str)
        or envelope_key_id != value.get("signing_key_id")
        or envelope_key_id != getattr(public_key, "key_id", None)
    ):
        return _result("KEY_ID_MISMATCH", lifecycle=lifecycle)
    try:
        encoded_signature = signature["signature"]
        if not isinstance(encoded_signature, str) or len(encoded_signature) > 128:
            raise ValueError
        raw_signature = base64.b64decode(encoded_signature, validate=True)
        if len(raw_signature) != 64:
            raise ValueError
        verifier = validate_ed25519_public_pem(public_key.public_key)
    except (ValueError, ValidationError, binascii.Error, AttributeError, TypeError, UnicodeError):
        return _result("INVALID_ENVELOPE", lifecycle=lifecycle)
    try:
        verifier.verify(raw_signature, stored)
    except InvalidSignature:
        return _result("INVALID_SIGNATURE", lifecycle=lifecycle)
    except Exception:
        return _result("VERIFICATION_ERROR", lifecycle=lifecycle)

    if lifecycle == SigningKeyStatus.REVOKED:
        return _result("VALID_REVOKED", crypto=True, lifecycle="revoked")
    if lifecycle not in {SigningKeyStatus.ACTIVE, SigningKeyStatus.VERIFY_ONLY}:
        return _result("VALID_UNTRUSTED_STATUS", crypto=True, lifecycle="invalid")
    current = now or datetime.now(datetime_timezone.utc)
    if current.tzinfo is None:
        return _result("VALID_UNTRUSTED_WINDOW", crypto=True, lifecycle=lifecycle)
    if current < public_key.valid_from or (
        public_key.valid_until is not None and current >= public_key.valid_until
    ):
        return _result("VALID_UNTRUSTED_WINDOW", crypto=True, lifecycle=lifecycle)
    return _result("VALID_TRUSTED", crypto=True, trusted=True, lifecycle=lifecycle)


def shareable_public_manifest(record) -> dict[str, object]:
    """Project only the externally shareable public pair and public metadata."""
    key = record.signing_key
    return {
        "payload": record.public_payload,
        "signature": record.public_signature_envelope,
        "public_key": {
            "key_id": key.key_id,
            "algorithm": key.algorithm,
            "public_key": key.public_key,
            "status": key.status,
            "valid_from": key.valid_from.isoformat(),
            "valid_until": key.valid_until.isoformat() if key.valid_until else None,
            "revoked_at": key.revoked_at.isoformat() if key.revoked_at else None,
        },
    }
