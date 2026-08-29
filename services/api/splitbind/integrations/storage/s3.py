from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

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


class S3ObjectStorage:
    """R2-compatible, exact-key S3 adapter. It intentionally has no list operation."""

    def __init__(self, *, bucket: str, client):
        if not bucket:
            raise ImproperlyConfigured("SPLITBIND_STORAGE_BUCKET is required")
        self.bucket = bucket
        self.client = client

    @classmethod
    def from_settings(cls):
        endpoint = getattr(settings, "SPLITBIND_STORAGE_ENDPOINT", "")
        bucket = getattr(settings, "SPLITBIND_STORAGE_BUCKET", "")
        access_key = getattr(settings, "SPLITBIND_STORAGE_ACCESS_KEY_ID", "")
        secret_key = getattr(settings, "SPLITBIND_STORAGE_SECRET_ACCESS_KEY", "")
        if not all((endpoint, bucket, access_key, secret_key)):
            raise ImproperlyConfigured("R2 storage endpoint, bucket, and credentials are required")
        import boto3

        return cls(
            bucket=bucket,
            client=boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name="auto",
            ),
        )

    def _call(self, operation, *args, **kwargs):
        try:
            return getattr(self.client, operation)(*args, **kwargs)
        except Exception as error:
            raise StorageUnavailable("storage provider request failed") from error

    def presign_put(self, *, key, content_type, size_bytes, sha256, expires):
        validate_put_constraints(key, content_type, size_bytes, sha256, expires)
        signed_url = self._call(
            "generate_presigned_url",
            "put_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ContentType": content_type,
                "ContentLength": size_bytes,
                "Metadata": {"sha256": sha256},
            },
            ExpiresIn=int(expires.total_seconds()),
            HttpMethod="PUT",
        )
        return PresignedPut(signed_url, {"Content-Length": str(size_bytes), "Content-Type": content_type, "x-amz-meta-sha256": sha256})

    def head(self, *, key):
        validate_controlled_key(key)
        try:
            response = self.client.head_object(Bucket=self.bucket, Key=key)
        except KeyError:
            return None
        except Exception as error:
            code = str(getattr(error, "response", {}).get("Error", {}).get("Code", ""))
            name = error.__class__.__name__.lower()
            if code in {"404", "NoSuchKey", "NotFound"} or "notfound" in name or "nosuchkey" in name:
                return None
            raise StorageUnavailable("storage provider request failed") from error
        return ObjectMetadata(key, response["ContentLength"], response.get("ContentType"), response.get("Metadata", {}).get("sha256"))

    def presign_get(self, *, key, expires):
        validate_controlled_key(key)
        validate_expiry(expires)
        return self._call("generate_presigned_url", "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=int(expires.total_seconds()), HttpMethod="GET")

    def copy_verified(self, *, source, destination, sha256):
        validate_controlled_key(source)
        validate_controlled_key(destination)
        validate_checksum(sha256)
        self._call("copy_object", Bucket=self.bucket, Key=destination, CopySource={"Bucket": self.bucket, "Key": source}, MetadataDirective="COPY")
        copied = self.head(key=destination)
        if copied is None or copied.sha256 != sha256:
            try:
                self.delete(key=destination)
            except StorageUnavailable:
                pass
            raise UploadRejected("STORAGE_COPY_MISMATCH")
        return copied

    def delete(self, *, key):
        validate_controlled_key(key)
        self._call("delete_object", Bucket=self.bucket, Key=key)
