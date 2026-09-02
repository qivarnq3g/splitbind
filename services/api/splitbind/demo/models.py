from contextlib import contextmanager
from contextvars import ContextVar

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q

from splitbind.access.models import (
    ValidatedOrganizationManager,
    ValidatedOrganizationOwnedModel,
    ValidatedOrganizationQuerySet,
)
from splitbind.demo.capabilities import DEMO_ALGORITHM_LABEL
from splitbind.documents.models import VerificationStatus
from splitbind.integrations.storage.base import validate_issuance_output_key
from splitbind.validators import SHA256_PATTERN, validate_sha256


DEMO_CANONICAL_CANVAS = (2304, 1152)
DEMO_FROZEN_CANDIDATE_IDENTIFIER = (
    "5342463201e7490f80b69ef1a3289afce40ef02989c9a4d89f00b916055cbf1c4"
    "c83a97b880000000240380000000000003ff8000000000000000001800000001200"
    "00000300000003"
)
DEMO_LIMITATIONS = (
    "fingerprint.experimental_unreleased_v2",
    "fingerprint.not_gate_g1_evidence",
    "evidence.not_proof_of_leak_edit_or_distribution",
)
DEMO_VERIFICATION_LIMITATIONS = (*DEMO_LIMITATIONS, "integrity.not_evaluated")
DEMO_STALE_RECOVERY_FENCE_CODE = "DEMO_STALE_RECOVERY_FENCED"
_DEMO_VERIFICATION_EVIDENCE_KEYS = {
    "algorithm_label",
    "decode_status",
    "fingerprint_confidence",
    "valid_vote_count",
    "analyzed_page_count",
    "manifest_signature_valid",
    "exact_file_hash_match",
    "limitations",
}
_DEMO_VERIFICATION_METRIC_KEYS = {
    "processing_ms",
    "pages_processed",
    "cleanup_failures",
}
_DEMO_VERIFICATION_DECODE_STATUSES = {
    "decoded",
    "partial_payload_evidence",
    "payload_not_detected",
    "insufficient_sync_evidence",
    "geometry_rejected",
}
_DEMO_VERIFICATION_ALLOWED_LIMITATIONS = {
    *DEMO_VERIFICATION_LIMITATIONS,
    "evidence.exact_hash_ambiguous",
    "evidence.retained_issuance_invalid",
    "fingerprint.decoded_source_not_available",
    "fingerprint.no_watermark_not_exclusion",
    "fingerprint.partial_payload_evidence",
    "manifest.signed_evidence_unavailable",
}


class DemoOutputState(models.TextChoices):
    RESERVED = "reserved", "Reserved"
    UPLOADING = "uploading", "Uploading"
    COMMITTED = "committed", "Committed"
    CLEANUP_REQUIRED = "cleanup_required", "Cleanup required"
    CLEANED = "cleaned", "Cleaned"


class DemoIssuanceResultQuerySet(ValidatedOrganizationQuerySet):
    _EVIDENCE_FIELDS = {
        "job",
        "job_id",
        "issuance",
        "issuance_id",
        "attempt",
        "owner_token",
        "output_object_key",
        "output_state",
        "algorithm_label",
        "candidate_identifier",
        "canvas_height",
        "canvas_width",
        "input_sha256",
        "output_sha256",
        "page_count",
        "processing_ms",
        "limitations",
        "cleanup_failures",
        "safe_error_code",
        "created_at",
        "updated_at",
    }

    def update(self, **kwargs):
        if self._EVIDENCE_FIELDS & kwargs.keys():
            raise ValidationError("demo issuance result evidence is immutable")
        return super().update(**kwargs)

    def delete(self):
        raise ValidationError("demo issuance result evidence must be preserved")

    def bulk_update(self, objs, fields, **kwargs):
        if self._EVIDENCE_FIELDS & set(fields):
            raise ValidationError("demo issuance result evidence is immutable")
        return super().bulk_update(objs, fields, **kwargs)

    def bulk_create(self, objs, **kwargs):
        raise ValidationError("demo issuance result evidence must use the result service")


class DemoIssuanceResultManager(
    ValidatedOrganizationManager.from_queryset(DemoIssuanceResultQuerySet)
):
    pass


_demo_result_write = ContextVar("demo_result_write", default=False)
_demo_result_recovery_transfer = ContextVar(
    "demo_result_recovery_transfer",
    default=False,
)


@contextmanager
def _allow_demo_result_write():
    token = _demo_result_write.set(True)
    try:
        yield
    finally:
        _demo_result_write.reset(token)


@contextmanager
def _allow_demo_result_recovery_transfer():
    token = _demo_result_recovery_transfer.set(True)
    try:
        yield
    finally:
        _demo_result_recovery_transfer.reset(token)


class DemoIssuanceResult(ValidatedOrganizationOwnedModel):
    objects = DemoIssuanceResultManager()
    job = models.OneToOneField(
        "jobs.Job",
        primary_key=True,
        on_delete=models.PROTECT,
        related_name="demo_issuance_result",
    )
    issuance = models.OneToOneField(
        "documents.Issuance",
        on_delete=models.PROTECT,
        related_name="demo_result",
    )
    attempt = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(2)]
    )
    owner_token = models.UUIDField(unique=True, editable=False)
    output_object_key = models.CharField(max_length=1024, unique=True)
    output_state = models.CharField(
        max_length=24,
        choices=DemoOutputState.choices,
        default=DemoOutputState.RESERVED,
    )
    algorithm_label = models.CharField(max_length=64, null=True, blank=True)
    candidate_identifier = models.CharField(
        max_length=146,
        validators=[RegexValidator(r"^[0-9a-f]{146}$")],
        null=True,
        blank=True,
    )
    canvas_height = models.PositiveIntegerField(null=True, blank=True)
    canvas_width = models.PositiveIntegerField(null=True, blank=True)
    input_sha256 = models.CharField(
        max_length=64,
        validators=[validate_sha256],
        null=True,
        blank=True,
    )
    output_sha256 = models.CharField(
        max_length=64,
        validators=[validate_sha256],
        null=True,
        blank=True,
    )
    page_count = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True,
        blank=True,
    )
    processing_ms = models.PositiveIntegerField(null=True, blank=True)
    limitations = models.JSONField(default=list, blank=True)
    cleanup_failures = models.PositiveSmallIntegerField(default=0)
    safe_error_code = models.CharField(max_length=80, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"
        indexes = [
            models.Index(
                fields=["output_state", "updated_at"],
                name="demo_result_cleanup_idx",
            )
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(output_state__in=DemoOutputState.values),
                name="demo_result_state_stable",
            ),
            models.CheckConstraint(
                condition=Q(attempt__gte=0, attempt__lte=2),
                name="demo_result_attempt_0_2",
            ),
            models.CheckConstraint(
                condition=Q(input_sha256__isnull=True)
                | Q(input_sha256__regex=SHA256_PATTERN),
                name="demo_result_input_sha256",
            ),
            models.CheckConstraint(
                condition=Q(output_sha256__isnull=True)
                | Q(output_sha256__regex=SHA256_PATTERN),
                name="demo_result_output_sha256",
            ),
            models.CheckConstraint(
                condition=~Q(output_state=DemoOutputState.COMMITTED)
                | (
                    Q(algorithm_label=DEMO_ALGORITHM_LABEL)
                    & Q(candidate_identifier=DEMO_FROZEN_CANDIDATE_IDENTIFIER)
                    & Q(canvas_height=DEMO_CANONICAL_CANVAS[0])
                    & Q(canvas_width=DEMO_CANONICAL_CANVAS[1])
                    & Q(input_sha256__isnull=False)
                    & Q(output_sha256__isnull=False)
                    & Q(page_count__gte=1, page_count__lte=5)
                    & Q(processing_ms__isnull=False)
                    & Q(limitations=list(DEMO_LIMITATIONS))
                    & Q(cleanup_failures=0)
                    & Q(safe_error_code__isnull=True)
                ),
                name="demo_result_committed_complete",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        self.validate_organization_relations(self.job, self.issuance)
        if self.job_id and self.issuance_id:
            if (
                self.job.kind != "issuance"
                or self.job.issuance_id != self.issuance_id
                or self.job.attempt != self.attempt
            ):
                raise ValidationError("demo result must bind its issuance job")
            expected_key = (
                f"outputs/issuance/{self.organization_id}/{self.issuance_id}.pdf"
            )
            if self.output_object_key != expected_key:
                raise ValidationError("demo result output key does not match its owner")
        try:
            validate_issuance_output_key(self.output_object_key)
        except ValueError as error:
            raise ValidationError("demo result output key is invalid") from error

        success_values = (
            self.algorithm_label,
            self.candidate_identifier,
            self.canvas_height,
            self.canvas_width,
            self.input_sha256,
            self.output_sha256,
            self.page_count,
            self.processing_ms,
        )
        if self.output_state == DemoOutputState.COMMITTED:
            if any(value is None for value in success_values):
                raise ValidationError("committed demo result evidence is incomplete")
            if (
                self.algorithm_label != DEMO_ALGORITHM_LABEL
                or self.candidate_identifier != DEMO_FROZEN_CANDIDATE_IDENTIFIER
                or (self.canvas_height, self.canvas_width) != DEMO_CANONICAL_CANVAS
                or self.limitations != list(DEMO_LIMITATIONS)
                or self.cleanup_failures != 0
                or self.safe_error_code is not None
            ):
                raise ValidationError("committed demo result evidence is invalid")
        elif any(value is not None for value in success_values) or self.limitations:
            raise ValidationError("uncommitted demo result cannot claim success evidence")
        if (
            self.output_state == DemoOutputState.CLEANUP_REQUIRED
            and (
                self.safe_error_code is None
                or (
                    self.safe_error_code != DEMO_STALE_RECOVERY_FENCE_CODE
                    and self.cleanup_failures < 1
                )
            )
        ):
            raise ValidationError("cleanup-required demo result needs durable failure evidence")

    def save(self, *args, **kwargs) -> None:
        if not _demo_result_write.get():
            raise ValidationError("demo issuance result evidence is immutable")
        if not self._state.adding:
            persisted = type(self)._base_manager.get(pk=self.pk)
            identity_fields = {
                "organization_id",
                "job_id",
                "issuance_id",
                "attempt",
                "owner_token",
                "output_object_key",
                "created_at",
            }
            changed_identity = {
                field
                for field in identity_fields
                if getattr(self, field) != getattr(persisted, field)
            }
            recovery_transfer = (
                _demo_result_recovery_transfer.get()
                and changed_identity == {"owner_token"}
                and persisted.output_state
                in {DemoOutputState.UPLOADING, DemoOutputState.CLEANUP_REQUIRED}
                and self.output_state == DemoOutputState.CLEANUP_REQUIRED
            )
            if changed_identity and not recovery_transfer:
                raise ValidationError("demo issuance result ownership is immutable")
            if persisted.output_state == DemoOutputState.COMMITTED:
                raise ValidationError("committed demo issuance result evidence is immutable")
            allowed_transitions = {
                DemoOutputState.RESERVED: {
                    DemoOutputState.UPLOADING,
                    DemoOutputState.CLEANED,
                },
                DemoOutputState.UPLOADING: {
                    DemoOutputState.COMMITTED,
                    DemoOutputState.CLEANUP_REQUIRED,
                    DemoOutputState.CLEANED,
                },
                DemoOutputState.CLEANUP_REQUIRED: {
                    DemoOutputState.CLEANUP_REQUIRED,
                    DemoOutputState.CLEANED,
                },
                DemoOutputState.CLEANED: {DemoOutputState.CLEANED},
            }
            if self.output_state not in allowed_transitions[persisted.output_state]:
                raise ValidationError("demo issuance result state transition is invalid")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("demo issuance result evidence must be preserved")


class DemoVerificationState(models.TextChoices):
    RESERVED = "reserved", "Reserved"
    COMMITTED = "committed", "Committed"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"


class DemoVerificationResultQuerySet(ValidatedOrganizationQuerySet):
    _EVIDENCE_FIELDS = {
        "job",
        "job_id",
        "verification",
        "verification_id",
        "attempt",
        "owner_token",
        "result_state",
        "input_sha256",
        "result_status",
        "recovered_issuance",
        "recovered_issuance_id",
        "evidence",
        "metrics",
        "safe_error_code",
        "completed_at",
        "created_at",
        "updated_at",
    }

    def update(self, **kwargs):
        if self._EVIDENCE_FIELDS & kwargs.keys():
            raise ValidationError("demo verification result evidence is immutable")
        return super().update(**kwargs)

    def delete(self):
        raise ValidationError("demo verification result evidence must be preserved")

    def bulk_update(self, objs, fields, **kwargs):
        if self._EVIDENCE_FIELDS & set(fields):
            raise ValidationError("demo verification result evidence is immutable")
        return super().bulk_update(objs, fields, **kwargs)

    def bulk_create(self, objs, **kwargs):
        raise ValidationError("demo verification result evidence must use the result service")


class DemoVerificationResultManager(
    ValidatedOrganizationManager.from_queryset(DemoVerificationResultQuerySet)
):
    pass


class DemoVerificationResult(ValidatedOrganizationOwnedModel):
    objects = DemoVerificationResultManager()
    job = models.OneToOneField(
        "jobs.Job",
        primary_key=True,
        on_delete=models.PROTECT,
        related_name="demo_verification_result",
    )
    verification = models.OneToOneField(
        "documents.Verification",
        on_delete=models.PROTECT,
        related_name="demo_result",
    )
    attempt = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(2)]
    )
    owner_token = models.UUIDField(unique=True, editable=False)
    result_state = models.CharField(
        max_length=16,
        choices=DemoVerificationState.choices,
        default=DemoVerificationState.RESERVED,
    )
    input_sha256 = models.CharField(
        max_length=64,
        validators=[validate_sha256],
        null=True,
        blank=True,
    )
    result_status = models.CharField(
        max_length=32,
        choices=VerificationStatus.choices,
        null=True,
        blank=True,
    )
    recovered_issuance = models.ForeignKey(
        "documents.Issuance",
        on_delete=models.PROTECT,
        related_name="demo_verification_results",
        null=True,
        blank=True,
    )
    evidence = models.JSONField(default=dict, blank=True)
    metrics = models.JSONField(default=dict, blank=True)
    safe_error_code = models.CharField(max_length=80, null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"
        constraints = [
            models.CheckConstraint(
                condition=Q(result_state__in=DemoVerificationState.values),
                name="demo_verify_state_stable",
            ),
            models.CheckConstraint(
                condition=Q(attempt__gte=0, attempt__lte=2),
                name="demo_verify_attempt_0_2",
            ),
            models.CheckConstraint(
                condition=Q(input_sha256__isnull=True)
                | Q(input_sha256__regex=SHA256_PATTERN),
                name="demo_verify_input_sha256",
            ),
            models.CheckConstraint(
                condition=Q(result_status__isnull=True)
                | Q(result_status__in=VerificationStatus.values),
                name="demo_verify_status_stable",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        self.validate_organization_relations(
            self.job,
            self.verification,
            self.recovered_issuance,
        )
        if self.job_id and self.verification_id and (
            self.job.kind != "verification"
            or self.job.verification_id != self.verification_id
            or self.job.attempt != self.attempt
        ):
            raise ValidationError("demo result must bind its verification job")

        result_values = (
            self.input_sha256,
            self.result_status,
            self.recovered_issuance_id,
            self.completed_at,
        )
        if self.result_state == DemoVerificationState.RESERVED:
            if (
                any(value is not None for value in result_values)
                or self.evidence
                or self.metrics
                or self.safe_error_code is not None
            ):
                raise ValidationError("reserved demo verification cannot claim result evidence")
        elif self.result_state == DemoVerificationState.COMMITTED:
            if (
                self.input_sha256 is None
                or self.result_status is None
                or self.result_status == VerificationStatus.PROCESSING_FAILED
                or self.completed_at is None
                or self.safe_error_code is not None
                or not isinstance(self.evidence, dict)
                or not isinstance(self.metrics, dict)
                or self.evidence.get("algorithm_label") != DEMO_ALGORITHM_LABEL
            ):
                raise ValidationError("committed demo verification evidence is incomplete")
            if (
                set(self.evidence) != _DEMO_VERIFICATION_EVIDENCE_KEYS
                or set(self.metrics) != _DEMO_VERIFICATION_METRIC_KEYS
            ):
                raise ValidationError("committed demo verification evidence shape is invalid")
            confidence = self.evidence["fingerprint_confidence"]
            valid_votes = self.evidence["valid_vote_count"]
            analyzed_pages = self.evidence["analyzed_page_count"]
            limitations = self.evidence["limitations"]
            metric_values = tuple(self.metrics.values())
            if (
                self.evidence["decode_status"]
                not in _DEMO_VERIFICATION_DECODE_STATUSES
                or isinstance(confidence, bool)
                or not isinstance(confidence, (int, float))
                or not 0.0 <= confidence <= 1.0
                or isinstance(valid_votes, bool)
                or not isinstance(valid_votes, int)
                or valid_votes < 0
                or isinstance(analyzed_pages, bool)
                or not isinstance(analyzed_pages, int)
                or not 1 <= analyzed_pages <= 5
                or not isinstance(self.evidence["exact_file_hash_match"], bool)
                or self.evidence["manifest_signature_valid"] not in (True, False, None)
                or not isinstance(limitations, list)
                or tuple(limitations[: len(DEMO_VERIFICATION_LIMITATIONS)])
                != DEMO_VERIFICATION_LIMITATIONS
                or len(limitations) != len(set(limitations))
                or any(
                    limitation not in _DEMO_VERIFICATION_ALLOWED_LIMITATIONS
                    for limitation in limitations
                )
                or any(
                    isinstance(value, bool) or not isinstance(value, int) or value < 0
                    for value in metric_values
                )
                or self.metrics["pages_processed"] != analyzed_pages
                or self.metrics["cleanup_failures"] != 0
            ):
                raise ValidationError("committed demo verification evidence shape is invalid")
        elif self.result_state == DemoVerificationState.FAILED:
            if (
                self.result_status != VerificationStatus.PROCESSING_FAILED
                or self.recovered_issuance_id is not None
                or self.completed_at is None
                or self.safe_error_code is None
            ):
                raise ValidationError("failed demo verification evidence is incomplete")
        elif self.result_state == DemoVerificationState.CANCELLED:
            if (
                self.result_status is not None
                or self.recovered_issuance_id is not None
                or self.completed_at is None
                or self.safe_error_code != "DEMO_JOB_CANCELLED"
            ):
                raise ValidationError("cancelled demo verification evidence is incomplete")

    def save(self, *args, **kwargs) -> None:
        if not _demo_result_write.get():
            raise ValidationError("demo verification result evidence is immutable")
        if not self._state.adding:
            persisted = type(self)._base_manager.get(pk=self.pk)
            identity_fields = {
                "organization_id",
                "job_id",
                "verification_id",
                "attempt",
                "owner_token",
                "created_at",
            }
            if any(
                getattr(self, field) != getattr(persisted, field)
                for field in identity_fields
            ):
                raise ValidationError("demo verification result ownership is immutable")
            if persisted.result_state != DemoVerificationState.RESERVED:
                raise ValidationError("terminal demo verification result evidence is immutable")
            if self.result_state == DemoVerificationState.RESERVED:
                raise ValidationError("demo verification result must make terminal progress")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("demo verification result evidence must be preserved")
