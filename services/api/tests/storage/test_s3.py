import hashlib
import uuid

import pytest

from splitbind.integrations.storage.base import StorageUnavailable, UploadRejected
from splitbind.integrations.storage.fake import FakeObjectStorage
from splitbind.integrations.storage.s3 import S3ObjectStorage


SHA256 = hashlib.sha256(b"real object bytes").hexdigest()


def promoted_key() -> str:
    return f"inputs/issuance/{uuid.uuid4()}/{uuid.uuid4()}.bin"


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
