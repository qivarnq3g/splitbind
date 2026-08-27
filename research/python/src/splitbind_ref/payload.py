"""Encode and validate the frozen SplitBind fingerprint payload."""

from __future__ import annotations

import zlib
from dataclasses import dataclass
from uuid import UUID

from .contracts import payload_profile


@dataclass(frozen=True, slots=True)
class PayloadDecode:
    issuance_id: UUID
    version: int


def encode_payload(issuance_id: UUID, version: int = 1) -> bytes:
    profile = payload_profile()
    payload_contract = profile["payload"]
    if version != profile["schema_version"]:
        raise ValueError(f"unsupported payload version: {version}")
    if not isinstance(issuance_id, UUID):
        raise TypeError("issuance_id must be a UUID")

    body = (
        payload_contract["magic_ascii"].encode("ascii")
        + version.to_bytes(payload_contract["schema_version_bytes"], "big")
        + issuance_id.bytes
    )
    checksum = zlib.crc32(body).to_bytes(payload_contract["crc32_bytes"], "big")
    return body + checksum


def verify_crc(payload: bytes) -> bool:
    profile = payload_profile()
    payload_contract = profile["payload"]
    input_bytes = profile["crc32"]["input_bytes"]
    checksum_bytes = payload_contract["crc32_bytes"]
    if len(payload) != payload_contract["total_bytes"]:
        return False
    expected = zlib.crc32(payload[:input_bytes]).to_bytes(checksum_bytes, "big")
    return expected == payload[input_bytes:]


def decode_payload(encoded: bytes) -> PayloadDecode:
    profile = payload_profile()
    payload_contract = profile["payload"]
    expected_length = payload_contract["total_bytes"]
    if len(encoded) != expected_length:
        raise ValueError(f"payload length must be {expected_length} bytes")

    magic = payload_contract["magic_ascii"].encode("ascii")
    if not encoded.startswith(magic):
        raise ValueError("invalid payload magic")

    version_offset = len(magic)
    version_end = version_offset + payload_contract["schema_version_bytes"]
    version = int.from_bytes(encoded[version_offset:version_end], "big")
    if version != profile["schema_version"]:
        raise ValueError(f"unsupported payload version: {version}")
    if not verify_crc(encoded):
        raise ValueError("payload CRC mismatch")

    issuance_end = version_end + payload_contract["issuance_uuid_bytes"]
    return PayloadDecode(
        issuance_id=UUID(bytes=encoded[version_end:issuance_end]),
        version=version,
    )
