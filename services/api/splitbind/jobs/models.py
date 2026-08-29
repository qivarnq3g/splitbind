import uuid

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from splitbind.access.models import OrganizationOwnedModel


class JobKind(models.TextChoices):
    ISSUANCE = "issuance", "Issuance"
    VERIFICATION = "verification", "Verification"


class JobStatus(models.TextChoices):
    CREATED = "created", "Created"
    QUEUED = "queued", "Queued"
    PROCESSING = "processing", "Processing"
    RETRYABLE_FAILED = "retryable_failed", "Retryable failed"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    DEAD_LETTERED = "dead_lettered", "Dead lettered"
    CANCELLED = "cancelled", "Cancelled"


class Job(OrganizationOwnedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=24, choices=JobKind.choices)
    status = models.CharField(
        max_length=32,
        choices=JobStatus.choices,
        default=JobStatus.CREATED,
    )
    attempt = models.PositiveSmallIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(2)],
    )
    issuance = models.ForeignKey(
        "documents.Issuance",
        on_delete=models.PROTECT,
        related_name="jobs",
        null=True,
        blank=True,
    )
    verification = models.ForeignKey(
        "documents.Verification",
        on_delete=models.PROTECT,
        related_name="jobs",
        null=True,
        blank=True,
    )
    deadline_at = models.DateTimeField()
    correlation_id = models.UUIDField()
    cancel_requested_at = models.DateTimeField(null=True, blank=True)
    safe_error_code = models.CharField(max_length=80, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(attempt__gte=0) & Q(attempt__lte=2),
                name="job_attempt_0_2",
            ),
            models.CheckConstraint(
                condition=(
                    Q(kind=JobKind.ISSUANCE, issuance__isnull=False, verification__isnull=True)
                    | Q(kind=JobKind.VERIFICATION, issuance__isnull=True, verification__isnull=False)
                ),
                name="job_kind_target_match",
            ),
            models.CheckConstraint(
                condition=Q(kind__in=JobKind.values),
                name="job_kind_stable",
            ),
            models.CheckConstraint(
                condition=Q(status__in=JobStatus.values),
                name="job_status_stable",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "status", "created_at"], name="job_org_status_idx"),
            models.Index(fields=["status", "deadline_at"], name="job_status_deadline_idx"),
            models.Index(fields=["correlation_id"], name="job_correlation_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        self.validate_organization_relations(self.issuance, self.verification)


class JobResultReceipt(OrganizationOwnedModel):
    message_id = models.UUIDField(primary_key=True, editable=False)
    job = models.ForeignKey(
        Job,
        on_delete=models.PROTECT,
        related_name="result_receipts",
    )
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["organization", "received_at"], name="receipt_org_received_idx")
        ]

    def clean(self) -> None:
        super().clean()
        self.validate_organization_relations(self.job)
