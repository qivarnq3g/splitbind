import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from splitbind.access.models import OrganizationOwnedModel
from splitbind.validators import SHA256_PATTERN, validate_sha256


class UploadPurpose(models.TextChoices):
    ISSUANCE = "issuance", "Issuance"
    VERIFICATION = "verification", "Verification"


class UploadRequest(OrganizationOwnedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="upload_requests",
    )
    purpose = models.CharField(max_length=16, choices=UploadPurpose.choices)
    object_key = models.CharField(max_length=1024, unique=True)
    sha256 = models.CharField(
        max_length=64,
        validators=[validate_sha256],
        null=True,
        blank=True,
    )
    size_bytes = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    expires_at = models.DateTimeField()
    finalized_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(sha256__isnull=True) | Q(sha256__regex=SHA256_PATTERN),
                name="upload_sha256_canonical",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "purpose", "created_at"], name="upload_org_purpose_idx"),
            models.Index(fields=["finalized_at", "expires_at"], name="upload_retention_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        self.validate_organization_relations(self.requested_by)
