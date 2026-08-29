import os
import uuid
from datetime import timedelta
from urllib.parse import urlparse

import pytest

from splitbind.integrations.storage.base import ObjectMetadata
from splitbind.integrations.storage.s3 import S3ObjectStorage


SHA256 = "a" * 64


class StubS3Client:
    def __init__(self):
        self.calls = []
        self.objects = {}

    def generate_presigned_url(self, operation, **kwargs):
        self.calls.append((operation, kwargs))
        return "https://example.invalid/presigned?credential=not-a-real-secret"

    def head_object(self, **kwargs):
        self.calls.append(("head_object", kwargs))
        return self.objects[kwargs["Key"]]

    def copy_object(self, **kwargs):
        self.calls.append(("copy_object", kwargs))
        source = kwargs["CopySource"]["Key"]
        self.objects[kwargs["Key"]] = dict(self.objects[source])

    def delete_object(self, **kwargs):
        self.calls.append(("delete_object", kwargs))
        self.objects.pop(kwargs["Key"], None)


def valid_key(kind="issuance_input"):
    return f"uploads/orphan/{kind}/{uuid.uuid4()}/{uuid.uuid4().hex}.bin"


def promoted_key(source, kind="issuance"):
    return f"inputs/{kind}/{source.split('/')[3]}/{uuid.uuid4()}.bin"


def test_s3_adapter_uses_exact_operation_key_checksum_and_never_lists():
    client = StubS3Client()
    storage = S3ObjectStorage(bucket="test-bucket", client=client)
    key = valid_key()

    signed = storage.presign_put(
        key=key, content_type="application/pdf", size_bytes=7, sha256=SHA256, expires=timedelta(minutes=15)
    )
    assert signed.headers == {
        "Content-Length": "7",
        "Content-Type": "application/pdf",
        "x-amz-meta-sha256": SHA256,
    }
    assert client.calls == [
        ("put_object", {
            "Params": {"Bucket": "test-bucket", "Key": key, "ContentType": "application/pdf", "ContentLength": 7, "Metadata": {"sha256": SHA256}},
            "ExpiresIn": 900,
            "HttpMethod": "PUT",
        })
    ]
    assert "list" not in " ".join(call[0].lower() for call in client.calls)


def test_s3_adapter_heads_copies_and_deletes_only_controlled_keys():
    client = StubS3Client()
    storage = S3ObjectStorage(bucket="test-bucket", client=client)
    source = valid_key()
    destination = promoted_key(source)
    client.objects[source] = {"ContentLength": 7, "ContentType": "application/pdf", "Metadata": {"sha256": SHA256}}

    assert storage.head(key=source) == ObjectMetadata(source, 7, "application/pdf", SHA256)
    copied = storage.copy_verified(source=source, destination=destination, sha256=SHA256)
    assert copied.key == destination
    storage.delete(key=destination)
    assert any(call[0] == "copy_object" for call in client.calls)
    assert any(call[0] == "delete_object" for call in client.calls)
    with pytest.raises(ValueError):
        storage.delete(key="other-tenant/object.bin")


@pytest.mark.skipif(
    os.environ.get("SPLITBIND_RUN_MINIO_INTEGRATION") != "1",
    reason="set SPLITBIND_RUN_MINIO_INTEGRATION=1 and --storage-endpoint for an authorized MinIO runtime gate",
)
def test_minio_runtime_contract_is_opt_in(request):
    endpoint = request.config.getoption("--storage-endpoint")
    if not endpoint:
        pytest.fail("--storage-endpoint is required when SPLITBIND_RUN_MINIO_INTEGRATION=1")
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        pytest.fail("--storage-endpoint must be a safe HTTP(S) MinIO endpoint without credentials, query, or fragment")

    access_key = os.environ.get("SPLITBIND_MINIO_ACCESS_KEY", "splitbind-integration-test")
    secret_key = os.environ.get("SPLITBIND_MINIO_SECRET_KEY", "splitbind-integration-test-not-a-secret")
    bucket = os.environ.get("SPLITBIND_MINIO_BUCKET", "splitbind-integration")
    prefix = f"uploads/orphan/issuance_input/{uuid.uuid4()}/"
    source = f"{prefix}{uuid.uuid4().hex}.bin"
    destination = f"inputs/issuance/{source.split('/')[3]}/{uuid.uuid4()}.bin"
    body = b"splitbind-minio-integration"
    import hashlib
    import boto3

    checksum = hashlib.sha256(body).hexdigest()
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name="us-east-1",
    )
    storage = S3ObjectStorage(bucket=bucket, client=client)
    created_bucket = False
    owned_keys = [source, destination]
    try:
        try:
            client.head_bucket(Bucket=bucket)
        except Exception:
            if os.environ.get("SPLITBIND_MINIO_ALLOW_CREATE_BUCKET") != "1":
                pytest.fail("MinIO bucket is absent; explicitly set SPLITBIND_MINIO_ALLOW_CREATE_BUCKET=1 to create the test bucket")
            client.create_bucket(Bucket=bucket)
            created_bucket = True
        client.put_object(
            Bucket=bucket,
            Key=source,
            Body=body,
            ContentType="application/pdf",
            Metadata={"sha256": checksum},
        )
        observed = storage.head(key=source)
        assert observed is not None
        assert observed.size_bytes == len(body)
        assert observed.client_sha256_metadata == checksum
        copied = storage.copy_verified(source=source, destination=destination, sha256=checksum)
        assert copied.key == destination
    finally:
        cleanup_errors = []
        for key in reversed(owned_keys):
            try:
                storage.delete(key=key)
            except Exception as error:
                cleanup_errors.append(f"{key}: {type(error).__name__}")
        remaining = [key for key in owned_keys if storage.head(key=key) is not None]
        if created_bucket and not remaining:
            client.delete_bucket(Bucket=bucket)
        if cleanup_errors or remaining:
            pytest.fail(f"MinIO cleanup failed for controlled task keys: errors={cleanup_errors}, remaining={remaining}")
