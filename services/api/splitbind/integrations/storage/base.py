import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Mapping, Protocol

from django.conf import settings

from splitbind.validators import SHA256_PATTERN


_ORPHAN_KEY = re.compile(
    r"^uploads/orphan/(issuance_input|verification_input)/"
    r"(?P<organization>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/"
    r"(?P<object>[0-9a-f]{32})\.bin$"
)
_PROMOTED_KEY = re.compile(
    r"^inputs/(?P<kind>issuance|verification)/"
    r"(?P<organization>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/"
    r"(?P<upload>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\.bin$"
)
_ISSUANCE_OUTPUT_KEY = re.compile(
    r"^outputs/issuance/"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.pdf$"
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
    # This is untrusted client-supplied object metadata, not a provider-verified
    # digest of the stored bytes. Workers must stream and hash content.
    client_sha256_metadata: str | None


class ObjectStorage(Protocol):
    def presign_put(
        self, *, key: str, content_type: str, size_bytes: int, sha256: str, expires: timedelta
    ) -> PresignedPut: ...

    def head(self, *, key: str) -> ObjectMetadata | None: ...

    def presign_get(self, *, key: str, expires: timedelta) -> str: ...

    def copy_verified(self, *, source: str, destination: str, sha256: str) -> ObjectMetadata:
        """Copy and observe metadata; on mismatch, retain the destination for owned cleanup."""
        ...

    def delete(self, *, key: str) -> None: ...


def validate_controlled_key(key: str) -> None:
    """Accept only application-generated orphan or promoted input keys."""
    if not isinstance(key, str) or not (
        _ORPHAN_KEY.fullmatch(key) or _PROMOTED_KEY.fullmatch(key) or _ISSUANCE_OUTPUT_KEY.fullmatch(key)
    ):
        raise ValueError("storage key must use a controlled application shape")
    if any(character in key for character in ("\\", "\x00", "\r", "\n")) or ".." in key:
        raise ValueError("storage key must use a controlled application shape")


def validate_orphan_key(key: str):
    if not isinstance(key, str) or not (match := _ORPHAN_KEY.fullmatch(key)):
        raise ValueError("storage source key must use the controlled orphan-upload shape")
    return match


def validate_promoted_key(key: str):
    if not isinstance(key, str) or not (match := _PROMOTED_KEY.fullmatch(key)):
        raise ValueError("storage destination key must use the controlled promoted-input shape")
    return match


def validate_copy_boundary(source: str, destination: str) -> None:
    source_match = validate_orphan_key(source)
    destination_match = validate_promoted_key(destination)
    source_kind = source_match.group(1).removesuffix("_input")
    if (
        source_kind != destination_match.group("kind")
        or source_match.group("organization") != destination_match.group("organization")
    ):
        raise ValueError("storage copy must preserve the same organization and kind")


def validate_checksum(sha256: str) -> None:
    if not isinstance(sha256, str) or not re.fullmatch(SHA256_PATTERN, sha256):
        raise ValueError("storage checksum must be a canonical SHA-256")


def validate_expiry(expires: timedelta) -> None:
    if not isinstance(expires, timedelta) or not timedelta(seconds=1) <= expires <= timedelta(minutes=15):
        raise ValueError("storage expiry must be between one second and fifteen minutes")


def validate_put_constraints(key: str, content_type: str, size_bytes: int, sha256: str, expires: timedelta) -> None:
    validate_orphan_key(key)
    kind = key.split("/", 3)[2]
    if content_type not in _CONTENT_TYPES[kind]:
        raise ValueError("storage content type is not allowed for this upload kind")
    runtime_max = getattr(settings, "MAX_PDF_BYTES", MAX_UPLOAD_BYTES)
    if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or not 1 <= size_bytes <= runtime_max:
        raise ValueError("storage object size must be between one byte and ten MiB")
    validate_checksum(sha256)
    validate_expiry(expires)
