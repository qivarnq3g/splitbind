import uuid

from django.conf import settings
from django.db import models

from splitbind.access.models import OrganizationOwnedModel


class AuditOutcome(models.TextChoices):
    SUCCEEDED = "succeeded", "Succeeded"
    DENIED = "denied", "Denied"
    FAILED = "failed", "Failed"


class AuditEvent(OrganizationOwnedModel):
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

    class Meta:
        indexes = [
            models.Index(fields=["organization", "created_at"], name="audit_org_created_idx"),
            models.Index(fields=["organization", "action", "created_at"], name="audit_org_action_idx"),
            models.Index(fields=["correlation_id"], name="audit_correlation_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        self.validate_organization_relations(self.actor)
