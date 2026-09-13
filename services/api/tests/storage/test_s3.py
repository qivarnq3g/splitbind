import hashlib
import tracemalloc
import uuid

import pytest

from splitbind.integrations.storage.base import (
    StorageUnavailable,
    UploadRejected,
    collect_bounded_bytes,
)
from splitbind.integrations.storage.fake import FakeObjectStorage
from splitbind.integrations.storage import s3 as s3_module
from splitbind.integrations.storage.s3 import S3ObjectStorage


SHA256 = hashlib.sha256(b"real object bytes").hexdigest()


def promoted_key() -> str:
    return f"inputs/issuance/{uuid.uuid4()}/{uuid.uuid4()}.bin"


def test_bounded_collector_accepts_exact_limit_and_rejects_one_byte_over():
    assert collect_bounded_bytes((b"12", b"34"), 4) == b"1234"
    with pytest.raises(UploadRejected, match="STORAGE_BYTE_LIMIT"):
        collect_bounded_bytes((b"1234", b"5"), 4)


def test_bounded_collector_rejects_gross_chunk_without_copying_it():
    gross_chunk = b"x" * (1024 * 1024)
    tracemalloc.start()
    try:
        with pytest.raises(UploadRejected, match="STORAGE_BYTE_LIMIT"):
            collect_bounded_bytes((gross_chunk,), 1)
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert peak_bytes < 256 * 1024


class StreamingBody:
    def __init__(self, content: bytes):
        self.content = content
        self.offset = 0
        self.closed = False

    def read(self, amount: int) -> bytes:
        chunk = self.content[self.offset : self.offset + amount]
        self.offset += len(chunk)
        return chunk

    def close(self) -> None:
        self.closed = True


def test_s3_download_streams_exact_key_and_verifies_actual_bytes_not_metadata():
    key = promoted_key()
    body = StreamingBody(b"real object bytes")

    class Client:
        def __init__(self):
            self.calls = []

        def get_object(self, **kwargs):
            self.calls.append(("get_object", kwargs))
            return {
                "Body": body,
                "ContentLength": len(body.content),
                "ContentType": "application/pdf",
                "Metadata": {"sha256": "0" * 64},
            }

    client = Client()
    downloaded = S3ObjectStorage(bucket="bucket", client=client).download_bytes(
        key=key,
        max_bytes=len(body.content),
        expected_sha256=SHA256,
    )

    assert downloaded.data == b"real object bytes"
    assert downloaded.actual_sha256 == SHA256
    assert downloaded.content_type == "application/pdf"
    assert client.calls == [("get_object", {"Bucket": "bucket", "Key": key})]
    assert body.closed is True


def test_s3_download_rejects_actual_checksum_mismatch_even_when_metadata_matches():
    key = promoted_key()
    body = StreamingBody(b"tampered")

    class Client:
        def get_object(self, **kwargs):
            return {
                "Body": body,
                "ContentLength": len(body.content),
                "ContentType": "application/pdf",
                "Metadata": {"sha256": SHA256},
            }

    with pytest.raises(UploadRejected, match="STORAGE_CHECKSUM_MISMATCH"):
        S3ObjectStorage(bucket="bucket", client=Client()).download_bytes(
            key=key,
            max_bytes=len(body.content),
            expected_sha256=SHA256,
        )
    assert body.closed is True


def test_s3_download_enforces_ceiling_while_streaming():
    key = promoted_key()
    body = StreamingBody(b"12345")

    class Client:
        def get_object(self, **kwargs):
            return {
                "Body": body,
                # A provider header cannot relax the streaming ceiling.
                "ContentLength": 4,
                "ContentType": "application/pdf",
                "Metadata": {},
            }

    with pytest.raises(UploadRejected, match="STORAGE_BYTE_LIMIT"):
        S3ObjectStorage(bucket="bucket", client=Client()).download_bytes(
            key=key,
            max_bytes=4,
            expected_sha256=hashlib.sha256(body.content).hexdigest(),
        )
    assert body.closed is True


def test_s3_download_closes_closeable_unreadable_body():
    key = promoted_key()

    class UnreadableBody:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    body = UnreadableBody()

    class Client:
        def get_object(self, **kwargs):
            return {"Body": body, "ContentType": "application/pdf"}

    with pytest.raises(StorageUnavailable, match="provider request failed"):
        S3ObjectStorage(bucket="bucket", client=Client()).download_bytes(
            key=key,
            max_bytes=1,
            expected_sha256="0" * 64,
        )
    assert body.closed is True


def test_s3_download_maps_close_failure_after_success_to_safe_provider_error():
    key = promoted_key()

    class CloseFailureBody(StreamingBody):
        def close(self):
            self.closed = True
            raise RuntimeError("provider close detail")

    body = CloseFailureBody(b"real object bytes")

    class Client:
        def get_object(self, **kwargs):
            return {
                "Body": body,
                "ContentType": "application/pdf",
            }

    with pytest.raises(StorageUnavailable, match="storage response cleanup failed"):
        S3ObjectStorage(bucket="bucket", client=Client()).download_bytes(
            key=key,
            max_bytes=len(body.content),
            expected_sha256=SHA256,
        )
    assert body.closed is True


def test_s3_download_preserves_read_error_and_records_close_failure():
    key = promoted_key()

    class ReadAndCloseFailureBody:
        def __init__(self):
            self.closed = False

        def read(self, amount):
            raise RuntimeError("provider read detail")

        def close(self):
            self.closed = True
            raise RuntimeError("provider close detail")

    body = ReadAndCloseFailureBody()

    class Client:
        def get_object(self, **kwargs):
            return {"Body": body, "ContentType": "application/pdf"}

    with pytest.raises(StorageUnavailable, match="storage provider request failed") as caught:
        S3ObjectStorage(bucket="bucket", client=Client()).download_bytes(
            key=key,
            max_bytes=1,
            expected_sha256="0" * 64,
        )
    assert body.closed is True
    assert caught.value.__notes__ == ["storage response cleanup failed"]


def test_s3_download_preserves_checksum_error_and_records_close_failure():
    key = promoted_key()

    class CloseFailureBody(StreamingBody):
        def close(self):
            self.closed = True
            raise RuntimeError("provider close detail")

    body = CloseFailureBody(b"tampered")

    class Client:
        def get_object(self, **kwargs):
            return {"Body": body, "ContentType": "application/pdf"}

    with pytest.raises(UploadRejected, match="STORAGE_CHECKSUM_MISMATCH") as caught:
        S3ObjectStorage(bucket="bucket", client=Client()).download_bytes(
            key=key,
            max_bytes=len(body.content),
            expected_sha256=SHA256,
        )
    assert body.closed is True
    assert caught.value.__notes__ == ["storage response cleanup failed"]


def test_s3_upload_streams_bounded_chunks_and_records_actual_digest():
    key = f"outputs/issuance/{uuid.uuid4()}/{uuid.uuid4()}.pdf"

    class Client:
        def __init__(self):
            self.calls = []

        def put_object(self, **kwargs):
            self.calls.append(("put_object", kwargs))
            return {}

    client = Client()
    uploaded = S3ObjectStorage(bucket="bucket", client=client).upload_bytes(
        key=key,
        content_type="application/pdf",
        chunks=(chunk for chunk in (b"real ", b"object ", b"bytes")),
        max_bytes=len(b"real object bytes"),
    )

    assert uploaded.data == b"real object bytes"
    assert uploaded.actual_sha256 == SHA256
    assert client.calls == [
        (
            "put_object",
            {
                "Bucket": "bucket",
                "Key": key,
                "Body": b"real object bytes",
                "ContentLength": len(b"real object bytes"),
                "ContentType": "application/pdf",
                "Metadata": {"sha256": SHA256},
            },
        )
    ]


def test_s3_upload_rejects_oversize_stream_before_provider_write():
    key = f"outputs/issuance/{uuid.uuid4()}/{uuid.uuid4()}.pdf"

    class Client:
        def __init__(self):
            self.puts = []

        def put_object(self, **kwargs):
            self.puts.append(kwargs)

    client = Client()
    with pytest.raises(UploadRejected, match="STORAGE_BYTE_LIMIT"):
        S3ObjectStorage(bucket="bucket", client=client).upload_bytes(
            key=key,
            content_type="application/pdf",
            chunks=(b"1234", b"5"),
            max_bytes=4,
        )
    assert client.puts == []


def test_byte_operations_reject_noncontrolled_keys_before_provider_access():
    class Client:
        def __getattr__(self, name):
            raise AssertionError(f"provider must not receive {name}")

    storage = S3ObjectStorage(bucket="bucket", client=Client())
    with pytest.raises(ValueError, match="controlled"):
        storage.download_bytes(
            key="inputs/issuance/../secret.pdf",
            max_bytes=1,
            expected_sha256="0" * 64,
        )
    with pytest.raises(ValueError, match="controlled"):
        storage.upload_bytes(
            key="outputs/issuance/../secret.pdf",
            content_type="application/pdf",
            chunks=(b"x",),
            max_bytes=1,
        )


def test_fake_keeps_metadata_only_helpers_byte_free_and_accepts_explicit_bytes():
    key = promoted_key()
    storage = FakeObjectStorage()
    storage.inject_object(
        key=key,
        content_type="application/pdf",
        size_bytes=len(b"real object bytes"),
        sha256="0" * 64,
    )

    with pytest.raises(StorageUnavailable, match="bytes unavailable"):
        storage.download_bytes(
            key=key,
            max_bytes=len(b"real object bytes"),
            expected_sha256=SHA256,
        )

    storage.inject_object_bytes(
        key=key,
        content_type="application/pdf",
        data=b"real object bytes",
        client_sha256_metadata="0" * 64,
    )
    downloaded = storage.download_bytes(
        key=key,
        max_bytes=len(b"real object bytes"),
        expected_sha256=SHA256,
    )
    assert downloaded.data == b"real object bytes"
    assert downloaded.actual_sha256 == SHA256


def test_fake_upload_retains_only_bounded_real_bytes_and_exact_delete_removes_them():
    key = f"outputs/issuance/{uuid.uuid4()}/{uuid.uuid4()}.pdf"
    storage = FakeObjectStorage()

    uploaded = storage.upload_bytes(
        key=key,
        content_type="application/pdf",
        chunks=(b"real ", b"object bytes"),
        max_bytes=len(b"real object bytes"),
    )

    assert uploaded.actual_sha256 == SHA256
    assert storage.objects[key].size_bytes == len(b"real object bytes")
    assert storage.objects[key].client_sha256_metadata == SHA256
    storage.delete(key=key)
    with pytest.raises(StorageUnavailable, match="bytes unavailable"):
        storage.download_bytes(
            key=key,
            max_bytes=len(b"real object bytes"),
            expected_sha256=SHA256,
        )


def test_fake_copy_propagates_only_explicitly_injected_bytes():
    organization_id = uuid.uuid4()
    source = f"uploads/orphan/issuance_input/{organization_id}/{uuid.uuid4().hex}.bin"
    destination = f"inputs/issuance/{organization_id}/{uuid.uuid4()}.bin"
    storage = FakeObjectStorage()
    storage.inject_object_bytes(
        key=source,
        content_type="application/pdf",
        data=b"real object bytes",
        client_sha256_metadata=SHA256,
    )

    storage.copy_verified(source=source, destination=destination, sha256=SHA256)

    downloaded = storage.download_bytes(
        key=destination,
        max_bytes=len(b"real object bytes"),
        expected_sha256=SHA256,
    )
    assert downloaded.data == b"real object bytes"


@pytest.mark.parametrize("metadata_operation", ["put_object", "inject_object"])
def test_fake_metadata_only_overwrite_invalidates_existing_bytes(metadata_operation):
    key = promoted_key()
    storage = FakeObjectStorage()
    storage.inject_object_bytes(
        key=key,
        content_type="application/pdf",
        data=b"real object bytes",
        client_sha256_metadata=SHA256,
    )

    getattr(storage, metadata_operation)(
        key=key,
        content_type="application/pdf",
        size_bytes=len(b"real object bytes"),
        sha256=SHA256,
    )

    with pytest.raises(StorageUnavailable, match="bytes unavailable"):
        storage.download_bytes(
            key=key,
            max_bytes=len(b"real object bytes"),
            expected_sha256=SHA256,
        )


def test_fake_metadata_only_copy_invalidates_existing_destination_bytes():
    organization_id = uuid.uuid4()
    source = f"uploads/orphan/issuance_input/{organization_id}/{uuid.uuid4().hex}.bin"
    destination = f"inputs/issuance/{organization_id}/{uuid.uuid4()}.bin"
    storage = FakeObjectStorage()
    storage.inject_object(
        key=source,
        content_type="application/pdf",
        size_bytes=len(b"real object bytes"),
        sha256=SHA256,
    )
    storage.inject_object_bytes(
        key=destination,
        content_type="application/pdf",
        data=b"real object bytes",
        client_sha256_metadata=SHA256,
    )

    storage.copy_verified(source=source, destination=destination, sha256=SHA256)

    with pytest.raises(StorageUnavailable, match="bytes unavailable"):
        storage.download_bytes(
            key=destination,
            max_bytes=len(b"real object bytes"),
            expected_sha256=SHA256,
        )


def test_fake_explicit_byte_conversion_fails_before_metadata_mutation():
    key = promoted_key()
    storage = FakeObjectStorage()

    class InvalidBytes:
        def __len__(self):
            return 1

        def __bytes__(self):
            raise TypeError("invalid bytes")

    with pytest.raises(TypeError, match="invalid bytes"):
        storage.inject_object_bytes(
            key=key,
            content_type="application/pdf",
            data=InvalidBytes(),
            client_sha256_metadata=SHA256,
        )

    assert key not in storage.objects
    assert key not in storage.object_bytes


def test_s3_client_is_built_with_bounded_timeouts_and_capped_retries(monkeypatch):
    captured = {}

    class _Boto3Stub:
        @staticmethod
        def client(service, **kwargs):
            captured["service"] = service
            captured["kwargs"] = kwargs
            return object()

    monkeypatch.setitem(__import__("sys").modules, "boto3", _Boto3Stub)
    monkeypatch.setattr(
        S3ObjectStorage, "validate_configuration", classmethod(lambda cls, **kwargs: None)
    )

    monkeypatch.setattr(
        s3_module.settings, "OBJECT_STORAGE_ENDPOINT", "https://example.invalid", raising=False
    )
    monkeypatch.setattr(s3_module.settings, "OBJECT_STORAGE_BUCKET", "bucket", raising=False)
    monkeypatch.setattr(s3_module.settings, "OBJECT_STORAGE_ACCESS_KEY", "key", raising=False)
    monkeypatch.setattr(s3_module.settings, "OBJECT_STORAGE_SECRET_KEY", "secret", raising=False)

    S3ObjectStorage.from_settings()

    config = captured["kwargs"]["config"]
    assert config.connect_timeout == s3_module.CONNECT_TIMEOUT_SECONDS
    assert config.read_timeout == s3_module.READ_TIMEOUT_SECONDS
    assert config.retries["max_attempts"] == s3_module.MAX_ATTEMPTS
    assert config.retries["mode"] == "standard"
    assert config.connect_timeout < 60 and config.read_timeout < 60
