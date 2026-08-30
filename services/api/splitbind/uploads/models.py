import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from splitbind.access.models import (
    ValidatedOrganizationManager,
    ValidatedOrganizationOwnedModel,
    ValidatedOrganizationQuerySet,
)
from splitbind.validators import SHA256_PATTERN, validate_sha256


MAX_UPLOAD_BYTES = 10 * 1024 * 1024


class UploadPurpose(models.TextChoices):
    ISSUANCE = "issuance", "Issuance"
    VERIFICATION = "verification", "Verification"


class PromotionStatus(models.TextChoices):
    NONE = "none", "None"
    COPYING = "copying", "Copying"
    ATTACHED = "attached", "Attached"
    FAILED = "failed", "Failed"


class UploadRequestQuerySet(ValidatedOrganizationQuerySet):
    _IMMUTABLE_FIELDS = {
        "purpose", "object_key", "expected_sha256", "size_bytes", "expires_at",
        "promotion_target_key", "promotion_status", "promotion_status_changed_at",
        "safe_error_code",
    }

    def update(self, **kwargs):
        deletion_fields = {"orphan_deleted_at", "promotion_target_deleted_at"} & kwargs.keys()
        if deletion_fields:
            raise ValidationError("deletion evidence requires the retention service")
        immutable = self._IMMUTABLE_FIELDS & kwargs.keys()
        if immutable:
            names = ", ".join(sorted(immutable))
            raise ValueError(f"upload intent fields are immutable ({names})")
        return super().update(**kwargs)

    def bulk_create(self, objs, **kwargs):
        if kwargs.get("update_conflicts"):
            raise ValidationError("conflict updates cannot rewrite upload evidence")
        objects = tuple(objs)
        if any(
            record.orphan_deleted_at is not None
            or record.promotion_target_deleted_at is not None
            for record in objects
        ):
            raise ValidationError("deletion evidence requires the retention service")
        return super().bulk_create(objects, **kwargs)


class UploadRequestManager(ValidatedOrganizationManager.from_queryset(UploadRequestQuerySet)):
    pass


class UploadRequest(ValidatedOrganizationOwnedModel):
    objects = UploadRequestManager()
    _IMMUTABLE_FIELDS = (
        "purpose", "object_key", "expected_sha256", "size_bytes", "expires_at",
        "promotion_target_key", "promotion_status", "promotion_status_changed_at",
        "safe_error_code",
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="upload_requests",
    )
    purpose = models.CharField(max_length=16, choices=UploadPurpose.choices)
    object_key = models.CharField(max_length=1024, unique=True)
    expected_sha256 = models.CharField(
        max_length=64,
        validators=[validate_sha256],
        null=True,
        blank=True,
    )
    size_bytes = models.PositiveBigIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_UPLOAD_BYTES)],
    )
    expires_at = models.DateTimeField()
    finalized_at = models.DateTimeField(null=True, blank=True)
    orphan_deleted_at = models.DateTimeField(null=True, blank=True)
    promotion_target_key = models.CharField(max_length=1024, null=True, blank=True)
    promotion_status = models.CharField(
        max_length=16, choices=PromotionStatus.choices, default=PromotionStatus.NONE,
    )
    promotion_status_changed_at = models.DateTimeField(auto_now_add=True)
    safe_error_code = models.CharField(max_length=80, null=True, blank=True)
    promotion_target_deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"
        constraints = [
            models.CheckConstraint(
                condition=Q(expected_sha256__isnull=True) | Q(expected_sha256__regex=SHA256_PATTERN),
                name="upload_expected_sha256_canonical",
            ),
            models.CheckConstraint(
                condition=Q(size_bytes__isnull=True) | Q(size_bytes__gte=1, size_bytes__lte=MAX_UPLOAD_BYTES),
                name="upload_size_legacy_null_or_bounded",
            ),
            models.CheckConstraint(
                condition=Q(promotion_status__in=PromotionStatus.values),
                name="upload_promotion_status_stable",
            ),
            models.CheckConstraint(
                condition=(
                    Q(promotion_status=PromotionStatus.NONE, promotion_target_key__isnull=True)
                    | Q(promotion_status__in=[PromotionStatus.COPYING, PromotionStatus.ATTACHED, PromotionStatus.FAILED], promotion_target_key__isnull=False)
                ),
                name="upload_promotion_target_state",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(promotion_status=PromotionStatus.FAILED)
                    | Q(safe_error_code__isnull=False)
                ),
                name="upload_failed_has_safe_code",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "purpose", "created_at"], name="upload_org_purpose_idx"),
            models.Index(fields=["finalized_at", "expires_at"], name="upload_retention_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        self.validate_organization_relations(self.requested_by)
        if self._state.adding:
            if self.expected_sha256 is None:
                raise ValidationError("new upload intent requires an expected checksum")
            if self.size_bytes is None or not 1 <= self.size_bytes <= MAX_UPLOAD_BYTES:
                raise ValidationError("new upload intent size must be between one byte and ten MiB")

    def save(self, *args, **kwargs) -> None:
        if self._state.adding and (
            self.orphan_deleted_at is not None or self.promotion_target_deleted_at is not None
        ):
            from splitbind.retention.capabilities import deletion_evidence_write_allowed
            if not deletion_evidence_write_allowed():
                raise ValidationError("deletion evidence requires the retention service")
        if not self._state.adding:
            update_fields = kwargs.get("update_fields")
            deletion_fields = {"orphan_deleted_at", "promotion_target_deleted_at"}
            names = set(update_fields) if update_fields is not None else deletion_fields
            if names & deletion_fields:
                persisted_deletions = type(self)._base_manager.only(*deletion_fields).get(pk=self.pk)
                changed_deletions = {
                    name for name in deletion_fields
                    if getattr(self, name) != getattr(persisted_deletions, name)
                }
                if changed_deletions:
                    from splitbind.retention.capabilities import deletion_evidence_write_allowed
                    if not deletion_evidence_write_allowed():
                        raise ValidationError("deletion evidence requires the retention service")
                    for name in changed_deletions:
                        if getattr(persisted_deletions, name) is not None or getattr(self, name) is None:
                            raise ValidationError("deletion evidence is monotonic")
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

    @transaction.atomic
    def save_promotion(
        self, *, status: str, target_key: str | None, safe_error_code: str | None,
    ) -> None:
        """The sole application path allowed to mutate durable promotion ownership."""
        if status not in PromotionStatus.values:
            raise ValueError("promotion status is invalid")
        if (status == PromotionStatus.NONE) != (target_key is None):
            raise ValueError("promotion target and state do not match")
        if status == PromotionStatus.FAILED and not safe_error_code:
            raise ValueError("failed promotion requires a safe error code")
        if status != PromotionStatus.FAILED and safe_error_code is not None:
            raise ValueError("only failed promotion may retain a safe error code")

        persisted = type(self)._base_manager.select_for_update().only(
            "promotion_status", "promotion_status_changed_at", "promotion_target_key",
            "safe_error_code", "promotion_target_deleted_at",
        ).get(pk=self.pk)
        if persisted.promotion_target_deleted_at is not None:
            raise ValueError(
                "deleted promotion target is permanently fenced; create a new upload reservation"
            )
        if (
            status == persisted.promotion_status
            and target_key == persisted.promotion_target_key
            and safe_error_code == persisted.safe_error_code
        ):
            return
        allowed = {
            PromotionStatus.NONE: {PromotionStatus.COPYING},
            PromotionStatus.COPYING: {PromotionStatus.ATTACHED, PromotionStatus.FAILED},
            PromotionStatus.FAILED: {PromotionStatus.COPYING},
            PromotionStatus.ATTACHED: set(),
        }
        if status not in allowed[persisted.promotion_status]:
            raise ValueError("promotion transition is invalid")
        if (
            persisted.promotion_target_key is not None
            and target_key != persisted.promotion_target_key
        ):
            raise ValueError("promotion target is immutable after reservation")
        if target_key is not None:
            from splitbind.integrations.storage.base import validate_promoted_key

            match = validate_promoted_key(target_key)
            expected_kind = "issuance" if self.purpose == UploadPurpose.ISSUANCE else "verification"
            if (
                match.group("kind") != expected_kind
                or match.group("organization") != str(self.organization_id)
                or match.group("upload") != str(self.id)
            ):
                raise ValueError("promotion target must identify this upload, organization, and purpose")
        at = timezone.now()
        if timezone.is_naive(at):
            raise ValueError("promotion transition time must be timezone-aware")
        self.promotion_status = status
        self.promotion_status_changed_at = at
        self.promotion_target_key = target_key
        self.safe_error_code = safe_error_code
        super().save(update_fields=[
            "promotion_status", "promotion_status_changed_at", "promotion_target_key",
            "safe_error_code",
        ])
