import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q

from splitbind.access.models import ValidatedOrganizationOwnedModel


class OutboxEvent(ValidatedOrganizationOwnedModel):
    id = models.BigAutoField(primary_key=True)
    message_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    job = models.ForeignKey(
        "jobs.Job",
        on_delete=models.PROTECT,
        related_name="outbox_events",
    )
    attempt = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(2)]
    )
    topic = models.CharField(max_length=80)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(attempt__gte=0) & Q(attempt__lte=2),
                name="outbox_attempt_0_2",
            ),
            models.UniqueConstraint(
                fields=["job", "attempt"],
                name="outbox_job_attempt_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["published_at", "created_at"], name="outbox_pending_idx"),
            models.Index(fields=["organization", "created_at"], name="outbox_org_created_idx"),
        ]

    def clean(self) -> None:
        super().clean()
        self.validate_organization_relations(self.job)
