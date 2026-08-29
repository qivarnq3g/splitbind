import uuid
from contextvars import ContextVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from splitbind.access.models import (
    ValidatedOrganizationOwnedModel,
    ValidatedOrganizationQuerySet,
)


class AuditOutcome(models.TextChoices):
    SUCCEEDED = "succeeded", "Succeeded"
    DENIED = "denied", "Denied"
    FAILED = "failed", "Failed"


_record_event_creation_allowed = ContextVar("record_event_creation_allowed", default=False)


class AppendOnlyAuditQuerySet(ValidatedOrganizationQuerySet):
    def _reject_creation(self):
        raise ValidationError("Audit events can only be created through record_event.")

    def create(self, **kwargs):
        self._reject_creation()

    def get_or_create(self, defaults=None, **kwargs):
        self._reject_creation()

    def update_or_create(self, defaults=None, create_defaults=None, **kwargs):
        self._reject_creation()

    def bulk_create(self, objs, **kwargs):
        self._reject_creation()

    def update(self, **kwargs):
        raise ValidationError("Audit events are append-only.")

    def bulk_update(self, objs, fields, **kwargs):
        raise ValidationError("Audit events are append-only.")

    def delete(self):
        raise ValidationError("Audit events are append-only.")


class AppendOnlyAuditManager(models.Manager.from_queryset(AppendOnlyAuditQuerySet)):
    """Expose creation and reads while refusing application mutation paths."""


class AuditEvent(ValidatedOrganizationOwnedModel):
    """Application audit records are created only through ``record_event``.

    Raw SQL and Django's ``save_base()`` are framework internals, not supported
    application persistence paths; application code must use ``record_event``.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="audit_events",
        null=True,
        blank=True,
    )
    action = models.CharField(max_length=120)
    target_type = models.CharField(max_length=80)
    target_id = models.CharField(max_length=120)
    correlation_id = models.UUIDField()
    outcome = models.CharField(max_length=16, choices=AuditOutcome.choices)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    objects = AppendOnlyAuditManager()

    class Meta:
        base_manager_name = "objects"
        default_manager_name = "objects"
        indexes = [
            models.Index(fields=["organization", "created_at"], name="audit_org_created_idx"),
            models.Index(fields=["organization", "action", "created_at"], name="audit_org_action_idx"),
            models.Index(fields=["correlation_id"], name="audit_correlation_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        self.validate_organization_relations(self.actor)

    @classmethod
    def _create_from_record_event(cls, **kwargs):
        event = cls(**kwargs)
        token = _record_event_creation_allowed.set(True)
        try:
            event.save(force_insert=True)
        finally:
            _record_event_creation_allowed.reset(token)
        return event

    def save(self, *args, **kwargs) -> None:
        if not self._state.adding:
            raise ValidationError("Audit events are append-only.")
        if not _record_event_creation_allowed.get():
            raise ValidationError("Audit events can only be created through record_event.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Audit events are append-only.")
