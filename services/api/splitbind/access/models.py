import uuid

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class Role(models.TextChoices):
    ADMINISTRATOR = "administrator", "Administrator"
    ISSUER = "issuer", "Issuer"
    VERIFIER = "verifier", "Verifier"
    AUDITOR = "auditor", "Auditor"


class Organization(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=80, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["slug"]


class OrganizationOwnedModel(models.Model):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_records",
    )

    class Meta:
        abstract = True

    def validate_organization_relations(self, *records: models.Model | None) -> None:
        if self.organization_id is None:
            return
        if any(
            record is not None and record.organization_id != self.organization_id
            for record in records
        ):
            raise ValidationError("Related records must belong to the same organization.")


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="users",
    )
    role = models.CharField(max_length=16, choices=Role.choices)

    class Meta:
        indexes = [models.Index(fields=["organization", "role"], name="user_org_role_idx")]
        constraints = [
            models.CheckConstraint(
                condition=Q(role__in=Role.values),
                name="user_role_stable",
            )
        ]


class Recipient(OrganizationOwnedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    external_reference = models.CharField(max_length=120)
    display_name = models.CharField(max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "external_reference"],
                name="recipient_org_ref_uniq",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "created_at"], name="recipient_org_created_idx")
        ]


class SigningKeyStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    VERIFY_ONLY = "verify_only", "Verify only"
    REVOKED = "revoked", "Revoked"


class SigningKey(OrganizationOwnedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    key_id = models.CharField(max_length=120, unique=True)
    algorithm = models.CharField(max_length=20, default="Ed25519", editable=False)
    public_key = models.TextField()
    status = models.CharField(
        max_length=16,
        choices=SigningKeyStatus.choices,
        default=SigningKeyStatus.ACTIVE,
    )
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "status"], name="signkey_org_status_idx")
        ]
