import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from splitbind.access.models import (
    ValidatedOrganizationManager,
    ValidatedOrganizationOwnedModel,
    ValidatedOrganizationQuerySet,
)
from splitbind.validators import SHA256_PATTERN, validate_sha256


class UploadPurpose(models.TextChoices):
    ISSUANCE = "issuance", "Issuance"
    VERIFICATION = "verification", "Verification"


class UploadRequestQuerySet(ValidatedOrganizationQuerySet):
    _IMMUTABLE_FIELDS = {"purpose", "object_key", "sha256", "size_bytes", "expires_at"}

    def update(self, **kwargs):
        immutable = self._IMMUTABLE_FIELDS & kwargs.keys()
        if immutable:
            names = ", ".join(sorted(immutable))
            raise ValueError(f"upload intent fields are immutable ({names})")
        return super().update(**kwargs)


class UploadRequestManager(ValidatedOrganizationManager.from_queryset(UploadRequestQuerySet)):
    pass


class UploadRequest(ValidatedOrganizationOwnedModel):
    objects = UploadRequestManager()
    _IMMUTABLE_FIELDS = ("purpose", "object_key", "sha256", "size_bytes", "expires_at")
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
        validators=[MinValueValidator(1)],
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

    def save(self, *args, **kwargs) -> None:
        if not self._state.adding:
            update_fields = kwargs.get("update_fields")
            names = set(update_fields) if update_fields is not None else set(self._IMMUTABLE_FIELDS)
            immutable = names & set(self._IMMUTABLE_FIELDS)
            if immutable:
                persisted = type(self)._base_manager.only(*immutable).get(pk=self.pk)
                changed = [name for name in immutable if getattr(self, name) != getattr(persisted, name)]
                if changed:
                    raise ValueError(f"upload intent fields are immutable ({', '.join(sorted(changed))})")
        super().save(*args, **kwargs)
