from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import quote

from .base import (
    ObjectBytes,
    ObjectMetadata,
    PresignedPut,
    StorageUnavailable,
    UploadRejected,
    collect_bounded_bytes,
    validate_copy_boundary,
    validate_checksum,
    validate_download_filename,
    validate_controlled_key,
    validate_expiry,
    validate_put_constraints,
    verified_object_bytes,
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
        self.object_bytes: dict[str, bytes] = {}
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

    def inject_object_bytes(
        self,
        *,
        key: str,
        content_type: str,
        data: bytes,
        client_sha256_metadata: str,
    ) -> None:
        """Test-only hook for attaching real bytes without trusting their metadata digest."""
        validate_controlled_key(key)
        validate_checksum(client_sha256_metadata)
        converted = bytes(data)
        self._store_object(
            key=key,
            content_type=content_type,
            size_bytes=len(converted),
            sha256=client_sha256_metadata,
        )
        self.object_bytes[key] = converted

    def _store_object(self, *, key: str, content_type: str, size_bytes: int, sha256: str) -> None:
        candidate = ObjectMetadata(key, size_bytes, content_type, sha256)
        current = self.objects.get(key)
        if current is not None and current != candidate:
            raise UploadRejected("STORAGE_METADATA_IMMUTABLE")
        self.objects[key] = candidate
        self.object_bytes.pop(key, None)

    def head(self, *, key):
        validate_controlled_key(key)
        self._maybe_fail("head")
        return self.objects.get(key)

    def presign_get(self, *, key, expires, filename=None):
        validate_controlled_key(key)
        validate_expiry(expires)
        if filename is not None:
            validate_download_filename(filename)
        self._maybe_fail("presign_get")
        suffix = f"&filename={quote(filename)}" if filename else ""
        return f"https://fake-storage.invalid/{quote(key)}?signed=opaque{suffix}"

    def download_bytes(self, *, key: str, max_bytes: int, expected_sha256: str) -> ObjectBytes:
        validate_controlled_key(key)
        self._maybe_fail("download_bytes")
        if key not in self.object_bytes:
            raise StorageUnavailable("storage object bytes unavailable")
        data = collect_bounded_bytes((self.object_bytes[key],), max_bytes)
        metadata = self.objects[key]
        return verified_object_bytes(
            key=key,
            data=data,
            content_type=metadata.content_type,
            expected_sha256=expected_sha256,
        )

    def upload_bytes(self, *, key, content_type, chunks, max_bytes) -> ObjectBytes:
        validate_controlled_key(key)
        self._maybe_fail("upload_bytes")
        data = collect_bounded_bytes(chunks, max_bytes)
        uploaded = verified_object_bytes(
            key=key,
            data=data,
            content_type=content_type,
        )
        self._store_object(
            key=key,
            content_type=content_type,
            size_bytes=len(data),
            sha256=uploaded.actual_sha256,
        )
        self.object_bytes[key] = data
        return uploaded

    def copy_verified(self, *, source, destination, sha256):
        validate_copy_boundary(source, destination)
        validate_checksum(sha256)
        self._maybe_fail("copy_verified")
        original = self.objects.get(source)
        if original is None:
            raise UploadRejected("STORAGE_COPY_MISMATCH")
        copied = ObjectMetadata(
            destination,
            original.size_bytes,
            original.content_type,
            original.client_sha256_metadata,
        )
        self.objects[destination] = copied
        if source in self.object_bytes:
            self.object_bytes[destination] = self.object_bytes[source]
        else:
            self.object_bytes.pop(destination, None)
        if copied.client_sha256_metadata != sha256:
            raise UploadRejected("STORAGE_COPY_MISMATCH")
        return copied

    def delete(self, *, key):
        validate_controlled_key(key)
        self._maybe_fail("delete")
        self.objects.pop(key, None)
        self.object_bytes.pop(key, None)
