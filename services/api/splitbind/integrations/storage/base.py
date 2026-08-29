import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Mapping, Protocol
from uuid import UUID

from splitbind.validators import SHA256_PATTERN


_CONTROLLED_KEY = re.compile(
    r"^uploads/orphan/(issuance_input|verification_input)/"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/"
    r"[0-9a-f]{32}\.bin$"
)
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_CONTENT_TYPES = {
    "issuance_input": {"application/pdf"},
    "verification_input": {"application/pdf", "image/png", "image/jpeg"},
}


class StorageUnavailable(RuntimeError):
    """Provider failure whose details must never be returned to browser clients."""


class UploadRejected(ValueError):
    """A bounded, public-safe upload rejection code."""


@dataclass(frozen=True)
class PresignedPut:
    url: str
    headers: Mapping[str, str]


@dataclass(frozen=True)
class ObjectMetadata:
    key: str
    size_bytes: int
    content_type: str | None
    sha256: str | None


class ObjectStorage(Protocol):
    def presign_put(
        self, *, key: str, content_type: str, size_bytes: int, sha256: str, expires: timedelta
    ) -> PresignedPut: ...

    def head(self, *, key: str) -> ObjectMetadata | None: ...

    def presign_get(self, *, key: str, expires: timedelta) -> str: ...

    def copy_verified(self, *, source: str, destination: str, sha256: str) -> ObjectMetadata: ...

    def delete(self, *, key: str) -> None: ...


def validate_controlled_key(key: str) -> None:
    """Reject all but application-generated orphan upload keys at adapter boundaries."""
    if not isinstance(key, str) or not _CONTROLLED_KEY.fullmatch(key):
        raise ValueError("storage key must use the controlled orphan-upload shape")
    if any(character in key for character in ("\\", "\x00", "\r", "\n")) or ".." in key:
        raise ValueError("storage key must use the controlled orphan-upload shape")


def validate_checksum(sha256: str) -> None:
    if not isinstance(sha256, str) or not re.fullmatch(SHA256_PATTERN, sha256):
        raise ValueError("storage checksum must be a canonical SHA-256")


def validate_expiry(expires: timedelta) -> None:
    if not isinstance(expires, timedelta) or not timedelta(seconds=1) <= expires <= timedelta(minutes=15):
        raise ValueError("storage expiry must be between one second and fifteen minutes")


def validate_put_constraints(key: str, content_type: str, size_bytes: int, sha256: str, expires: timedelta) -> None:
    validate_controlled_key(key)
    kind = key.split("/", 3)[2]
    if content_type not in _CONTENT_TYPES[kind]:
        raise ValueError("storage content type is not allowed for this upload kind")
    if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or not 1 <= size_bytes <= MAX_UPLOAD_BYTES:
        raise ValueError("storage object size must be between one byte and ten MiB")
    validate_checksum(sha256)
    validate_expiry(expires)
