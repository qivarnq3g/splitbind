import uuid
from datetime import timedelta

from django.http import Http404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from splitbind.access.throttles import (
    AccountRateThrottle,
    IssuanceJobRateThrottle,
    SourceIPRateThrottle,
    VerificationJobRateThrottle,
)
from splitbind.audit.models import AuditOutcome
from splitbind.audit.services import record_event
from splitbind.documents.serializers import (
    IssuanceCreateSerializer,
    VerificationCreateSerializer,
    issuance_result_evidence,
    serialize_issuance,
    serialize_verification,
)
from splitbind.documents.services import get_issuance, get_verification
from splitbind.integrations.storage.base import StorageUnavailable, UploadRejected
from splitbind.jobs.services import (
    JobConflict,
    WorkflowNotFound,
    create_issuance,
    create_verification,
)
from splitbind.openapi import (
    issuance_create_schema,
    issuance_detail_schema,
    issuance_result_schema,
    verification_create_schema,
    verification_detail_schema,
)
from splitbind.uploads.services import get_storage


ISSUANCE_RESULT_TTL = timedelta(minutes=5)


def _serializer_denial(actor, action):
    record_event(
        actor, action, actor, AuditOutcome.DENIED, uuid.uuid4(),
        {"safe_error_code": "WORKFLOW_REQUEST"},
    )


def _error_response(error):
    if isinstance(error, WorkflowNotFound):
        raise Http404
    if isinstance(error, JobConflict):
        return Response({"code": str(error)}, status=409)
    return Response({"code": str(error)}, status=400)


@method_decorator(csrf_protect, name="dispatch")
class IssuanceCreateView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [AccountRateThrottle, SourceIPRateThrottle, IssuanceJobRateThrottle]

    @issuance_create_schema
    def post(self, request):
        serializer = IssuanceCreateSerializer(data=request.data)
        if not serializer.is_valid():
            _serializer_denial(request.user, "issuance.create_denied")
            return Response(serializer.errors, status=400)
        try:
            issuance, job = create_issuance(request.user, **serializer.validated_data)
        except (WorkflowNotFound, JobConflict, UploadRejected) as error:
            return _error_response(error)
        return Response(serialize_issuance(issuance, job), status=201)


class IssuanceDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @issuance_detail_schema
    def get(self, request, id):
        try:
            record = get_issuance(request.user, id)
        except WorkflowNotFound:
            raise Http404
        return Response(serialize_issuance(record))


class IssuanceResultView(APIView):
    permission_classes = [IsAuthenticated]

    @issuance_result_schema
    def get(self, request, id):
        try:
            record = get_issuance(request.user, id)
        except WorkflowNotFound:
            raise Http404
        evidence = issuance_result_evidence(record)
        if evidence is None:
            return Response({"code": "ISSUANCE_RESULT_UNAVAILABLE"}, status=409)
        expires_at = timezone.now() + ISSUANCE_RESULT_TTL
        try:
            download_url = get_storage().presign_get(
                key=evidence.output_object_key,
                expires=ISSUANCE_RESULT_TTL,
            )
        except StorageUnavailable:
            return Response({"code": "STORAGE_UNAVAILABLE"}, status=503)
        except ValueError:
            return Response({"code": "ISSUANCE_RESULT_UNAVAILABLE"}, status=409)
        return Response(
            {
                "download_url": download_url,
                "expires_at": expires_at.isoformat(),
            }
        )


@method_decorator(csrf_protect, name="dispatch")
class VerificationCreateView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [AccountRateThrottle, SourceIPRateThrottle, VerificationJobRateThrottle]

    @verification_create_schema
    def post(self, request):
        serializer = VerificationCreateSerializer(data=request.data)
        if not serializer.is_valid():
            _serializer_denial(request.user, "verification.create_denied")
            return Response(serializer.errors, status=400)
        try:
            verification, job = create_verification(request.user, **serializer.validated_data)
        except (WorkflowNotFound, JobConflict, UploadRejected) as error:
            return _error_response(error)
        return Response(serialize_verification(verification, job), status=201)


class VerificationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @verification_detail_schema
    def get(self, request, id):
        try:
            record = get_verification(request.user, id)
        except WorkflowNotFound:
            raise Http404
        return Response(serialize_verification(record))
