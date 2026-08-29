import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from splitbind.access.models import SigningKey, ValidatedOrganizationOwnedModel
from splitbind.uploads.models import UploadRequest
from splitbind.validators import SHA256_PATTERN, validate_sha256


class Document(ValidatedOrganizationOwnedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="documents_created",
    )
    upload_request = models.OneToOneField(
        UploadRequest,
        on_delete=models.PROTECT,
        related_name="document",
    )
    source_object_key = models.CharField(max_length=1024, unique=True)
    source_sha256 = models.CharField(max_length=64, validators=[validate_sha256])
    page_count = models.PositiveSmallIntegerField(validators=[MinValueValidator(1)])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(source_sha256__regex=SHA256_PATTERN),
                name="document_sha256_canonical",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "created_at"], name="document_org_created_idx")
        ]

    def clean(self) -> None:
        super().clean()
        self.validate_organization_relations(self.created_by, self.upload_request)


class Issuance(ValidatedOrganizationOwnedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        Document,
        on_delete=models.PROTECT,
        related_name="issuances",
    )
    recipient = models.ForeignKey(
        "access.Recipient",
        on_delete=models.PROTECT,
        related_name="issuances",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="issuances_created",
    )
    output_object_key = models.CharField(max_length=1024, unique=True, null=True, blank=True)
    output_sha256 = models.CharField(
        max_length=64,
        validators=[validate_sha256],
        null=True,
        blank=True,
    )
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(output_sha256__isnull=True) | Q(output_sha256__regex=SHA256_PATTERN),
                name="issuance_sha256_canonical",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "issued_at"], name="issuance_org_issued_idx"),
            models.Index(fields=["organization", "recipient"], name="issuance_org_recipient_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        self.validate_organization_relations(self.document, self.recipient, self.created_by)

    def public_payload(self) -> dict[str, str]:
        return {
            "issuance_id": str(self.id),
            "issued_at": self.issued_at.isoformat(),
            **({"output_sha256": self.output_sha256} if self.output_sha256 else {}),
        }


class Manifest(ValidatedOrganizationOwnedModel):
    issuance = models.OneToOneField(
        Issuance,
        on_delete=models.PROTECT,
        related_name="manifest",
    )
    signing_key = models.ForeignKey(
        SigningKey,
        on_delete=models.PROTECT,
        related_name="manifests",
    )
    internal_payload = models.TextField()
    internal_signature_envelope = models.JSONField()
    public_payload = models.TextField()
    public_signature_envelope = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "created_at"], name="manifest_org_created_idx")
        ]

    def clean(self) -> None:
        super().clean()
        self.validate_organization_relations(self.issuance, self.signing_key)


class VerificationStatus(models.TextChoices):
    VERIFIED_INTACT = "VERIFIED_INTACT", "Verified intact"
    SOURCE_IDENTIFIED_MODIFIED = "SOURCE_IDENTIFIED_MODIFIED", "Source identified, modified"
    PARTIAL_EVIDENCE = "PARTIAL_EVIDENCE", "Partial evidence"
    NO_WATERMARK = "NO_WATERMARK", "No watermark"
    INVALID_MANIFEST = "INVALID_MANIFEST", "Invalid manifest"
    PROCESSING_FAILED = "PROCESSING_FAILED", "Processing failed"


class Verification(ValidatedOrganizationOwnedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    upload_request = models.OneToOneField(
        UploadRequest,
        on_delete=models.PROTECT,
        related_name="verification",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="verifications_requested",
    )
    recovered_issuance = models.ForeignKey(
        Issuance,
        on_delete=models.PROTECT,
        related_name="verifications",
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=32,
        choices=VerificationStatus.choices,
        null=True,
        blank=True,
    )
    evidence = models.JSONField(default=dict, blank=True)
    metrics = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(status__isnull=True) | Q(status__in=VerificationStatus.values),
                name="verification_status_stable",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "created_at"], name="verify_org_created_idx"),
            models.Index(fields=["organization", "status"], name="verify_org_status_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        self.validate_organization_relations(
            self.upload_request,
            self.requested_by,
            self.recovered_issuance,
        )
