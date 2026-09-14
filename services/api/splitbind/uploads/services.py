import uuid
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone

from splitbind.access.models import Role
from splitbind.audit.models import AuditOutcome
from splitbind.audit.services import record_event
from splitbind.integrations.storage.base import (
    FORBIDDEN_FILENAME_CHARACTERS,
    StorageUnavailable,
    UploadRejected,
    validate_download_filename,
)
from splitbind.integrations.storage.s3 import S3ObjectStorage
from splitbind.uploads.models import UploadPurpose, UploadRequest
from splitbind.validators import SHA256_PATTERN


UPLOAD_TTL = timedelta(minutes=15)
_KIND_TO_PURPOSE = {
    "issuance_input": UploadPurpose.ISSUANCE,
    "verification_input": UploadPurpose.VERIFICATION,
}
_CONTENT_TYPES = {
    "issuance_input": {"application/pdf"},
    "verification_input": {"application/pdf", "image/png", "image/jpeg"},
}


@dataclass(frozen=True)
class UploadIntent:
    record: UploadRequest
    url: str
    required_headers: dict[str, str]


def get_storage():
    configured = getattr(settings, "SPLITBIND_OBJECT_STORAGE", None)
    return configured if configured is not None else S3ObjectStorage.from_settings()


def _record_denial(actor, action: str, code: str, *, kind: str = "") -> None:
    metadata = {"safe_error_code": code}
    if kind:
        metadata["kind"] = kind
    record_event(
        actor, action, actor, AuditOutcome.DENIED, uuid.uuid4(),
        metadata,
    )


def _reject(actor, code: str, *, action: str, kind: str = "") -> None:
    _record_denial(actor, action, code, kind=kind)
    raise UploadRejected(code)


def _authorize(actor, kind: str, *, action: str) -> None:
    allowed = (
        actor.role == Role.ADMINISTRATOR
        or (actor.role == Role.ISSUER and kind == "issuance_input")
        or (actor.role == Role.VERIFIER and kind == "verification_input")
    )
    if not allowed:
        _reject(actor, "UPLOAD_FORBIDDEN", action=action, kind=kind)


def _validate_intent(actor, *, kind: str, content_type: str, size_bytes: int, sha256: str) -> None:
    _authorize(actor, kind, action="upload.intent.denied")
    if kind not in _KIND_TO_PURPOSE:
        _reject(actor, "UPLOAD_KIND", action="upload.intent.denied", kind=kind)
    if content_type not in _CONTENT_TYPES[kind]:
        _reject(actor, "UPLOAD_CONTENT_TYPE", action="upload.intent.denied", kind=kind)
    if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or not 1 <= size_bytes <= settings.MAX_PDF_BYTES:
        _reject(actor, "UPLOAD_SIZE", action="upload.intent.denied", kind=kind)
    import re
    if not isinstance(sha256, str) or not re.fullmatch(SHA256_PATTERN, sha256):
        _reject(actor, "UPLOAD_SHA256", action="upload.intent.denied", kind=kind)


def safe_source_filename(filename: object) -> str:
    if not isinstance(filename, str):
        return ""
    candidate = filename.replace(chr(92), "/").rsplit("/", 1)[-1].strip()
    cleaned = "".join(
        character
        for character in candidate
        if ord(character) >= 32 and ord(character) != 127 and character not in FORBIDDEN_FILENAME_CHARACTERS
    ).strip()
    while cleaned.startswith("."):
        cleaned = cleaned[1:].strip()
    if len(cleaned) > 120:
        stem, separator, extension = cleaned.rpartition(".")
        cleaned = (stem[:120] + separator + extension) if separator else cleaned[:120]
    try:
        return validate_download_filename(cleaned)
    except ValueError:
        return ""


def create_upload(actor, *, kind: str, filename: str, content_type: str, size_bytes: int, sha256: str) -> UploadIntent:
    """Create an exact-key, 15-minute browser upload intent; filename never affects storage."""
    _validate_intent(actor, kind=kind, content_type=content_type, size_bytes=size_bytes, sha256=sha256)
    now = timezone.now()
    upload_id = uuid.uuid4()
    key = f"uploads/orphan/{kind}/{actor.organization_id}/{upload_id.hex}.bin"
    try:
        signed = get_storage().presign_put(
            key=key, content_type=content_type, size_bytes=size_bytes, sha256=sha256, expires=UPLOAD_TTL
        )
    except StorageUnavailable:
        _reject(actor, "STORAGE_UNAVAILABLE", action="upload.intent.denied", kind=kind)
    with transaction.atomic():
        record = UploadRequest.objects.create(
            id=upload_id,
            organization_id=actor.organization_id,
            requested_by=actor,
            purpose=_KIND_TO_PURPOSE[kind],
            object_key=key,
            source_filename=safe_source_filename(filename),
            expected_sha256=sha256,
            size_bytes=size_bytes,
            expires_at=now + UPLOAD_TTL,
        )
        record_event(
            actor, "upload.intent.created", record, AuditOutcome.SUCCEEDED, uuid.uuid4(),
            {"kind": kind, "object_size": size_bytes, "status": "pending"},
        )
    return UploadIntent(record, signed.url, dict(signed.headers))


def _kind_for(record: UploadRequest) -> str:
    return "issuance_input" if record.purpose == UploadPurpose.ISSUANCE else "verification_input"


def _scoped_upload(actor, upload_id, *, for_update: bool = False):
    queryset = UploadRequest.objects
    if for_update:
        queryset = queryset.select_for_update()
    queryset = queryset.filter(organization_id=actor.organization_id, id=upload_id)
    if actor.role != Role.ADMINISTRATOR:
        queryset = queryset.filter(requested_by_id=actor.id)
    try:
        return queryset.get()
    except ObjectDoesNotExist:
        _record_denial(actor, "upload.complete.denied", "UPLOAD_NOT_FOUND")
        raise UploadRejected("UPLOAD_NOT_FOUND")


def complete_upload(actor, *, upload_id, sha256: str) -> UploadRequest:
    kind = ""
    try:
        with transaction.atomic():
            upload = _scoped_upload(actor, upload_id, for_update=True)
            kind = _kind_for(upload)
            _authorize(actor, kind, action="upload.complete.denied")
            if sha256 != upload.expected_sha256:
                _reject(actor, "UPLOAD_METADATA_MISMATCH", action="upload.complete.denied", kind=kind)
            if upload.finalized_at is not None:
                return upload
            if timezone.now() >= upload.expires_at:
                _reject(actor, "UPLOAD_EXPIRED", action="upload.complete.denied", kind=kind)
            try:
                observed = get_storage().head(key=upload.object_key)
            except StorageUnavailable:
                _reject(actor, "STORAGE_UNAVAILABLE", action="upload.complete.denied", kind=kind)
            if timezone.now() >= upload.expires_at:
                _reject(actor, "UPLOAD_EXPIRED", action="upload.complete.denied", kind=kind)
            # The metadata digest is the immutable client expectation bound into
            # the signed PUT. It is not proof that provider bytes hash to it.
            if (
                observed is None
                or observed.size_bytes != upload.size_bytes
                or observed.client_sha256_metadata != upload.expected_sha256
            ):
                _reject(actor, "UPLOAD_METADATA_MISMATCH", action="upload.complete.denied", kind=kind)
            upload.finalized_at = timezone.now()
            upload.save(update_fields=["finalized_at"])
            record_event(
                actor, "upload.completed", upload, AuditOutcome.SUCCEEDED, uuid.uuid4(),
                {"kind": kind, "object_size": upload.size_bytes, "status": "ready"},
            )
        return upload
    except UploadRejected as error:
        # Any denial written inside the failed atomic block is rolled back.
        # Persist exactly one safe denial after rollback.
        _record_denial(actor, "upload.complete.denied", str(error), kind=kind)
        raise


def record_serializer_denial(actor, *, action: str, errors) -> None:
    """Audit serializer rejection with one allow-listed code and no input data."""
    field = next(iter(errors), "") if isinstance(errors, dict) else ""
    code_by_field = {
        "kind": "UPLOAD_KIND",
        "content_type": "UPLOAD_CONTENT_TYPE",
        "size_bytes": "UPLOAD_SIZE",
        "sha256": "UPLOAD_SHA256",
        "filename": "UPLOAD_FILENAME",
    }
    _record_denial(actor, action, code_by_field.get(field, "UPLOAD_REQUEST"))
