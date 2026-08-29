from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import quote

from .base import (
    ObjectMetadata,
    PresignedPut,
    StorageUnavailable,
    UploadRejected,
    validate_checksum,
    validate_controlled_key,
    validate_expiry,
    validate_put_constraints,
)


@dataclass(frozen=True)
class _ExpectedPut:
    content_type: str
    size_bytes: int
    sha256: str
    expires: timedelta


class FakeObjectStorage:
    """Network-free storage double with the same exact-key contract as S3."""

    def __init__(self):
        self.objects: dict[str, ObjectMetadata] = {}
        self.expected_puts: dict[str, _ExpectedPut] = {}
        self._failures: dict[str, str] = {}

    def fail_next(self, operation: str, detail: str = "provider failure") -> None:
        self._failures[operation] = detail

    def _maybe_fail(self, operation: str) -> None:
        if detail := self._failures.pop(operation, None):
            raise StorageUnavailable(detail)

    def presign_put(self, *, key, content_type, size_bytes, sha256, expires):
        validate_put_constraints(key, content_type, size_bytes, sha256, expires)
        self._maybe_fail("presign_put")
        self.expected_puts[key] = _ExpectedPut(content_type, size_bytes, sha256, expires)
        return PresignedPut(
            url=f"https://fake-storage.invalid/{quote(key)}?signed=opaque",
            headers={
                "Content-Length": str(size_bytes),
                "Content-Type": content_type,
                "x-amz-meta-sha256": sha256,
            },
        )

    def put_object(self, *, key: str, content_type: str, size_bytes: int, sha256: str) -> None:
        validate_controlled_key(key)
        validate_checksum(sha256)
        self._maybe_fail("put_object")
        expected = self.expected_puts.get(key)
        if expected is not None and (content_type, size_bytes, sha256) != (
            expected.content_type,
            expected.size_bytes,
            expected.sha256,
        ):
            raise UploadRejected("STORAGE_UPLOAD_CONSTRAINT")
        self._store_object(key=key, content_type=content_type, size_bytes=size_bytes, sha256=sha256)

    def inject_object(self, *, key: str, content_type: str, size_bytes: int, sha256: str) -> None:
        """Test-only provider observation hook; it does not model a signed browser PUT."""
        validate_controlled_key(key)
        validate_checksum(sha256)
        self._store_object(key=key, content_type=content_type, size_bytes=size_bytes, sha256=sha256)

    def _store_object(self, *, key: str, content_type: str, size_bytes: int, sha256: str) -> None:
        candidate = ObjectMetadata(key, size_bytes, content_type, sha256)
        current = self.objects.get(key)
        if current is not None and current != candidate:
            raise UploadRejected("STORAGE_METADATA_IMMUTABLE")
        self.objects[key] = candidate

    def head(self, *, key):
        validate_controlled_key(key)
        self._maybe_fail("head")
        return self.objects.get(key)

    def presign_get(self, *, key, expires):
        validate_controlled_key(key)
        validate_expiry(expires)
        self._maybe_fail("presign_get")
        return f"https://fake-storage.invalid/{quote(key)}?signed=opaque"

    def copy_verified(self, *, source, destination, sha256):
        validate_controlled_key(source)
        validate_controlled_key(destination)
        validate_checksum(sha256)
        self._maybe_fail("copy_verified")
        original = self.objects.get(source)
        if original is None or original.sha256 != sha256:
            self.objects.pop(destination, None)
            raise UploadRejected("STORAGE_COPY_MISMATCH")
        copied = ObjectMetadata(destination, original.size_bytes, original.content_type, original.sha256)
        self.objects[destination] = copied
        return copied

    def delete(self, *, key):
        validate_controlled_key(key)
        self._maybe_fail("delete")
        self.objects.pop(key, None)
