import uuid

from django.http import Http404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from splitbind.access.throttles import AccountRateThrottle, SourceIPRateThrottle
from splitbind.access.selectors import scope_jobs
from splitbind.audit.models import AuditOutcome
from splitbind.audit.services import record_event
from splitbind.jobs.models import Job
from splitbind.jobs.serializers import CancelJobSerializer, serialize_job
from splitbind.jobs.services import JobConflict, WorkflowNotFound, request_cancel


class JobDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, job_id):
        try:
            job = scope_jobs(request.user, Job.objects.all()).get(pk=job_id)
        except (Job.DoesNotExist, ValueError):
            raise Http404
        return Response(serialize_job(job))


@method_decorator(csrf_protect, name="dispatch")
class JobCancelView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [AccountRateThrottle, SourceIPRateThrottle]

    def post(self, request, job_id):
        serializer = CancelJobSerializer(data=request.data)
        if not serializer.is_valid():
            record_event(
                request.user, "job.cancel_denied", request.user, AuditOutcome.DENIED,
                uuid.uuid4(), {"safe_error_code": "WORKFLOW_REQUEST"},
            )
            return Response(serializer.errors, status=400)
        try:
            job = request_cancel(request.user, job_id, serializer.validated_data["correlation_id"])
        except WorkflowNotFound:
            raise Http404
        except JobConflict as error:
            return Response({"code": str(error)}, status=409)
        return Response(serialize_job(job))
