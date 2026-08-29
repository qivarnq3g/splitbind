import uuid

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from splitbind.access.models import Organization, Role
from splitbind.audit.models import AuditEvent, AuditOutcome
from splitbind.audit.services import record_event


@pytest.fixture
def audit_actor(db):
    organization = Organization.objects.create(name="Audit Organization", slug="audit-org")
    actor = get_user_model().objects.create_user(
        username="audit-admin",
        password="test-password-not-a-secret",
        organization=organization,
        role=Role.ADMINISTRATOR,
    )
    return actor


@pytest.mark.django_db
def test_record_event_normalizes_identifiers_and_drops_sensitive_metadata(audit_actor):
    correlation = uuid.uuid4()
    event = record_event(
        actor=audit_actor,
        action="auth.login",
        target=audit_actor,
        outcome=AuditOutcome.SUCCEEDED,
        correlation_id=str(correlation),
        metadata={
            "kind": "login",
            "role": Role.ADMINISTRATOR,
            "attempt": 1,
            "Password": "not-retained",
            "authorization": "Bearer secret",
            "session": "not-retained",
            "private_key": "not-retained",
            "pdf_content": "not-retained",
            "status": "https://storage.example.test/signed?credential=secret",
            "safe_error_code": "x" * 300,
            "object_size": {"nested": "value"},
        },
    )

    assert event.organization_id == audit_actor.organization_id
    assert event.actor_id == audit_actor.id
    assert event.target_type == "access.user"
    assert event.target_id == str(audit_actor.id)
    assert event.correlation_id == correlation
    assert event.metadata == {
        "kind": "login",
        "role": Role.ADMINISTRATOR,
        "attempt": "1",
        "safe_error_code": "x" * 256,
    }


@pytest.mark.django_db
def test_record_event_rejects_cross_organization_target_and_bad_correlation(audit_actor):
    other = Organization.objects.create(name="Other Audit Organization", slug="other-audit-org")
    target = get_user_model().objects.create_user(
        username="other-user",
        password="test-password-not-a-secret",
        organization=other,
        role=Role.ISSUER,
    )

    with pytest.raises(ValidationError, match="same organization"):
        record_event(audit_actor, "auth.login", target, AuditOutcome.DENIED, uuid.uuid4(), {})
    with pytest.raises(ValidationError, match="correlation"):
        record_event(audit_actor, "auth.login", audit_actor, AuditOutcome.DENIED, "not-a-uuid", {})


@pytest.mark.django_db
def test_audit_events_have_no_application_update_or_delete_path(audit_actor):
    event = record_event(
        audit_actor,
        "auth.login",
        audit_actor,
        AuditOutcome.SUCCEEDED,
        uuid.uuid4(),
        {"kind": "login"},
    )

    event.action = "altered"
    with pytest.raises(ValidationError, match="append-only"):
        event.save()
    with pytest.raises(ValidationError, match="append-only"):
        event.delete()
    with pytest.raises(ValidationError, match="append-only"):
        AuditEvent.objects.filter(pk=event.pk).update(action="altered")
    with pytest.raises(ValidationError, match="append-only"):
        AuditEvent.objects.filter(pk=event.pk).delete()
    with pytest.raises(ValidationError, match="append-only"):
        AuditEvent.objects.bulk_update([event], ["action"])
