from splitbind.access.selectors import scope_issuances, scope_verifications
from splitbind.documents.models import Issuance, Verification
from splitbind.jobs.services import WorkflowNotFound


def get_issuance(actor, record_id):
    try:
        return scope_issuances(actor, Issuance.objects.all()).get(pk=record_id)
    except (Issuance.DoesNotExist, ValueError) as error:
        raise WorkflowNotFound("WORKFLOW_NOT_FOUND") from error


def get_verification(actor, record_id):
    try:
        return scope_verifications(actor, Verification.objects.all()).get(pk=record_id)
    except (Verification.DoesNotExist, ValueError) as error:
        raise WorkflowNotFound("WORKFLOW_NOT_FOUND") from error
