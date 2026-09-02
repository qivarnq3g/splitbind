from datetime import timedelta
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .base import (
    ObjectBytes,
    ObjectMetadata,
    PresignedPut,
    StorageUnavailable,
    UploadRejected,
    collect_bounded_bytes,
    validate_copy_boundary,
    validate_checksum,
    validate_controlled_key,
    validate_expiry,
    validate_put_constraints,
    verified_object_bytes,
)


class S3ObjectStorage:
    """R2-compatible, exact-key S3 adapter. It intentionally has no list operation."""

    def __init__(self, *, bucket: str, client):
        if not bucket:
            raise ImproperlyConfigured("OBJECT_STORAGE_BUCKET is required")
        self.bucket = bucket
        self.client = client

    @classmethod
    def from_settings(cls):
        endpoint = getattr(settings, "OBJECT_STORAGE_ENDPOINT", "")
        bucket = getattr(settings, "OBJECT_STORAGE_BUCKET", "")
        access_key = getattr(settings, "OBJECT_STORAGE_ACCESS_KEY", "")
        secret_key = getattr(settings, "OBJECT_STORAGE_SECRET_KEY", "")
        cls.validate_configuration(
            endpoint=endpoint, bucket=bucket, access_key=access_key, secret_key=secret_key,
            environment=getattr(settings, "ENVIRONMENT", "production"),
            managed_hint=getattr(settings, "OBJECT_STORAGE_ENDPOINT_HINT", ""),
        )
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

    @classmethod
    def validate_settings_configuration(cls) -> None:
        cls.validate_configuration(
            endpoint=getattr(settings, "OBJECT_STORAGE_ENDPOINT", ""),
            bucket=getattr(settings, "OBJECT_STORAGE_BUCKET", ""),
            access_key=getattr(settings, "OBJECT_STORAGE_ACCESS_KEY", ""),
            secret_key=getattr(settings, "OBJECT_STORAGE_SECRET_KEY", ""),
            environment=getattr(settings, "ENVIRONMENT", "production"),
            managed_hint=getattr(settings, "OBJECT_STORAGE_ENDPOINT_HINT", ""),
        )

    @classmethod
    def validate_configuration(cls, *, endpoint, bucket, access_key, secret_key, environment, managed_hint):
        if not all((endpoint, bucket, access_key, secret_key)):
            raise ImproperlyConfigured("R2 storage endpoint, bucket, and credentials are required")
        cls._validate_endpoint(endpoint, environment=environment, managed_hint=managed_hint)

    @staticmethod
    def _validate_endpoint(endpoint: str, *, environment: str, managed_hint: str) -> None:
        if environment not in {"production", "local", "offline", "test"}:
            raise ImproperlyConfigured("object storage environment must be production, local, offline, or test")

        def parse(value: str):
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
                or any(character.isspace() or ord(character) < 32 for character in value)
            ):
                raise ImproperlyConfigured("object storage endpoint must be a safe HTTP(S) authority")
            try:
                port = parsed.port
            except ValueError as error:
                raise ImproperlyConfigured("object storage endpoint port is invalid") from error
            return parsed.scheme, parsed.hostname, port

        actual = parse(endpoint)
        if environment == "production":
            if actual[0] != "https":
                raise ImproperlyConfigured("production object storage endpoint must use HTTPS")
            if not managed_hint or parse(managed_hint) != actual:
                raise ImproperlyConfigured("production object storage endpoint must match the managed endpoint hint")
        elif actual[0] == "http" and environment not in {"local", "offline", "test"}:
            raise ImproperlyConfigured("HTTP object storage is allowed only in an explicit non-production environment")

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

    def download_bytes(self, *, key: str, max_bytes: int, expected_sha256: str) -> ObjectBytes:
        validate_controlled_key(key)
        validate_checksum(expected_sha256)
        response = self._call("get_object", Bucket=self.bucket, Key=key)
        body = response.get("Body")
        if body is None or not callable(getattr(body, "read", None)):
            raise StorageUnavailable("storage provider request failed")

        def chunks():
            streamed = 0
            while True:
                chunk = body.read(min(64 * 1024, max_bytes - streamed + 1))
                if not chunk:
                    return
                streamed += len(chunk)
                yield chunk

        try:
            data = collect_bounded_bytes(chunks(), max_bytes)
        except (UploadRejected, TypeError, ValueError):
            raise
        except Exception as error:
            raise StorageUnavailable("storage provider request failed") from error
        finally:
            close = getattr(body, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass
        return verified_object_bytes(
            key=key,
            data=data,
            content_type=response.get("ContentType"),
            expected_sha256=expected_sha256,
        )

    def upload_bytes(self, *, key, content_type, chunks, max_bytes) -> ObjectBytes:
        validate_controlled_key(key)
        data = collect_bounded_bytes(chunks, max_bytes)
        uploaded = verified_object_bytes(
            key=key,
            data=data,
            content_type=content_type,
        )
        self._call(
            "put_object",
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentLength=len(data),
            ContentType=content_type,
            Metadata={"sha256": uploaded.actual_sha256},
        )
        return uploaded

    def copy_verified(self, *, source, destination, sha256):
        validate_copy_boundary(source, destination)
        validate_checksum(sha256)
        self._call("copy_object", Bucket=self.bucket, Key=destination, CopySource={"Bucket": self.bucket, "Key": source}, MetadataDirective="COPY")
        copied = self.head(key=destination)
        if copied is None or copied.client_sha256_metadata != sha256:
            raise UploadRejected("STORAGE_COPY_MISMATCH")
        return copied

    def delete(self, *, key):
        validate_controlled_key(key)
        self._call("delete_object", Bucket=self.bucket, Key=key)
