import uuid

from django.core.exceptions import ValidationError

from splitbind.audit.models import AuditEvent, AuditOutcome
from splitbind.audit.redaction import redact_metadata


def _normalized_correlation_id(correlation_id) -> uuid.UUID:
    try:
        return uuid.UUID(str(correlation_id))
    except (TypeError, ValueError, AttributeError) as error:
        raise ValidationError("correlation_id must be a UUID") from error


def record_event(
    actor,
    action: str,
    target,
    outcome: str,
    correlation_id,
    metadata,
) -> AuditEvent:
    """Write one tenant-consistent, redacted audit event.

    This service is intentionally creation-only. AuditEvent rejects later
    application-level updates or deletes.
    """
    if actor is None or actor.organization_id is None:
        raise ValidationError("audit actor must belong to an organization")
    if actor.pk is None or actor._state.adding:
        raise ValidationError("audit actor must be persisted")
    if target is None or not hasattr(target, "organization_id"):
        raise ValidationError("audit target must be organization-owned")
    if target.pk is None or target._state.adding:
        raise ValidationError("audit target must be persisted")
    if target.organization_id != actor.organization_id:
        raise ValidationError("audit actor and target must belong to the same organization")
    if not isinstance(action, str) or not action or len(action) > 120:
        raise ValidationError("audit action must be a non-empty bounded string")
    if outcome not in AuditOutcome.values:
        raise ValidationError("audit outcome is invalid")

    target_type = target._meta.label_lower
    target_id = str(target.pk)
    if len(target_type) > 80 or len(target_id) > 120:
        raise ValidationError("audit target identifier is too long")

    return AuditEvent._create_from_record_event(
        organization_id=actor.organization_id,
        actor_id=actor.id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        correlation_id=_normalized_correlation_id(correlation_id),
        outcome=outcome,
        metadata=redact_metadata(metadata),
    )
