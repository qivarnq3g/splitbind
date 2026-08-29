import uuid

from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
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


class ValidatedOrganizationQuerySet(models.QuerySet):
    """Allow scalar state updates, but reject unchecked tenant/relation rewrites."""

    def _protected_bulk_fields(self) -> set[str]:
        protected = {"organization", "organization_id"}
        for field in self.model._meta.fields:
            if not isinstance(field, (models.ForeignKey, models.OneToOneField)):
                continue
            related_model = field.remote_field.model
            if hasattr(related_model, "organization_id"):
                protected.update({field.name, field.attname})
        return protected

    def update(self, **kwargs):
        protected = self._protected_bulk_fields() & kwargs.keys()
        if protected:
            names = ", ".join(sorted(protected))
            raise ValidationError(
                f"Unsafe bulk update of tenant or relation fields ({names}) is forbidden; "
                "load instances and save() them instead."
            )
        return super().update(**kwargs)

    def bulk_create(self, objs, **kwargs):
        objects = tuple(objs)
        for obj in objects:
            obj.validate_organization_persistence()
        return super().bulk_create(objects, **kwargs)

    def bulk_update(self, objs, fields, **kwargs):
        objects = tuple(objs)
        for obj in objects:
            obj.validate_organization_persistence()
        return super().bulk_update(objects, fields, **kwargs)


class ValidatedOrganizationManager(models.Manager.from_queryset(ValidatedOrganizationQuerySet)):
    """Default manager for organization-owned records with explicit bulk policy."""


class ValidatedOrganizationOwnedModel(OrganizationOwnedModel):
    objects = ValidatedOrganizationManager()

    class Meta:
        abstract = True

    def validate_organization_persistence(self) -> None:
        if not self._state.adding:
            try:
                persisted_organization_id = type(self)._base_manager.only(
                    "organization_id"
                ).get(pk=self.pk).organization_id
            except type(self).DoesNotExist as error:
                raise ValidationError(
                    "persisted organization record no longer exists"
                ) from error
            if self.organization_id != persisted_organization_id:
                raise ValidationError("organization cannot be changed after creation")
        self.clean()

    def save(self, *args, **kwargs) -> None:
        if self._state.adding:
            if args or kwargs.get("force_update") or kwargs.get("update_fields") is not None:
                raise ValueError("adding instance cannot use update-only save flags")
            kwargs["force_insert"] = True
        self.validate_organization_persistence()
        super().save(*args, **kwargs)


class UserManager(DjangoUserManager.from_queryset(ValidatedOrganizationQuerySet)):
    use_in_migrations = True

    def _organization(self, organization):
        if organization is None:
            raise ValueError("organization is required")
        if isinstance(organization, Organization):
            return organization
        try:
            return Organization.objects.get(pk=organization)
        except (Organization.DoesNotExist, ValidationError, ValueError) as error:
            raise ValueError("organization must identify an existing organization") from error

    def create_user(self, username, email=None, password=None, **extra_fields):
        organization = self._organization(extra_fields.pop("organization", None))
        role = extra_fields.pop("role", None)
        if role not in Role.values:
            raise ValueError("role must be a stable non-superuser role")
        if extra_fields.get("is_superuser", False):
            raise ValueError("create_user cannot set is_superuser")
        extra_fields["is_staff"] = role == Role.ADMINISTRATOR
        extra_fields["is_superuser"] = False
        return self._create_user(
            username,
            email,
            password,
            organization=organization,
            role=role,
            **extra_fields,
        )

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        organization = self._organization(extra_fields.pop("organization", None))
        role = extra_fields.pop("role", Role.ADMINISTRATOR)
        if role != Role.ADMINISTRATOR:
            raise ValueError("superusers must have the administrator role")
        if extra_fields.get("is_staff") is False:
            raise ValueError("superuser must have is_staff=True")
        if extra_fields.get("is_superuser") is False:
            raise ValueError("superuser must have is_superuser=True")
        extra_fields["is_staff"] = True
        extra_fields["is_superuser"] = True
        return self._create_user(
            username,
            email,
            password,
            organization=organization,
            role=role,
            **extra_fields,
        )


class User(ValidatedOrganizationOwnedModel, AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="users",
    )
    role = models.CharField(max_length=16, choices=Role.choices)
    objects = UserManager()

    REQUIRED_FIELDS = ["organization"]

    class Meta:
        indexes = [models.Index(fields=["organization", "role"], name="user_org_role_idx")]
        constraints = [
            models.CheckConstraint(
                condition=Q(role__in=Role.values),
                name="user_role_stable",
            )
        ]


class Recipient(ValidatedOrganizationOwnedModel):
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


class SigningKey(ValidatedOrganizationOwnedModel):
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
