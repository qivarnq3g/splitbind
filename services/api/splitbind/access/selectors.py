from django.db.models import QuerySet

from splitbind.access.models import Role, User
from splitbind.documents.models import Issuance, Verification
from splitbind.jobs.models import Job, JobKind


def scope_issuances(actor: User, queryset: QuerySet[Issuance]) -> QuerySet[Issuance]:
    """Return only issuance evidence the actor is permitted to discover."""
    scoped = queryset.filter(organization_id=actor.organization_id)
    if actor.role in {Role.ADMINISTRATOR, Role.AUDITOR}:
        return scoped
    if actor.role == Role.ISSUER:
        return scoped.filter(created_by_id=actor.id)
    return scoped.none()


def scope_verifications(actor: User, queryset: QuerySet[Verification]) -> QuerySet[Verification]:
    """Return only verification evidence the actor is permitted to discover."""
    scoped = queryset.filter(organization_id=actor.organization_id)
    if actor.role in {Role.ADMINISTRATOR, Role.AUDITOR}:
        return scoped
    if actor.role == Role.VERIFIER:
        return scoped.filter(requested_by_id=actor.id)
    return scoped.none()


def scope_jobs(actor: User, queryset: QuerySet[Job]) -> QuerySet[Job]:
    scoped = queryset.filter(organization_id=actor.organization_id)
    if actor.role in {Role.ADMINISTRATOR, Role.AUDITOR}:
        return scoped
    if actor.role == Role.ISSUER:
        return scoped.filter(kind=JobKind.ISSUANCE, issuance__created_by_id=actor.id)
    if actor.role == Role.VERIFIER:
        return scoped.filter(kind=JobKind.VERIFICATION, verification__requested_by_id=actor.id)
    return scoped.none()
