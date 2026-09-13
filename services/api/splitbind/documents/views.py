import uuid
from datetime import timedelta

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from splitbind.access.services import resolve_recipient_for_issue
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
from splitbind.documents.manifests import shareable_public_manifest
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
    issuance_manifest_schema,
    issuance_result_schema,
    verification_create_schema,
    verification_detail_schema,
)
from splitbind.uploads.services import get_storage


ISSUANCE_RESULT_TTL = timedelta(minutes=5)


def _manifest_audit(actor, target, outcome, *, safe_error_code=None):
    metadata = {}
    if safe_error_code is not None:
        metadata["safe_error_code"] = safe_error_code
    action = {
        AuditOutcome.SUCCEEDED: "issuance.manifest_shared",
        AuditOutcome.DENIED: "issuance.manifest_denied",
        AuditOutcome.FAILED: "issuance.manifest_failed",
    }[outcome]
    record_event(actor, action, target, outcome, uuid.uuid4(), metadata)


def _result_download_audit(actor, target, outcome, *, safe_error_code=None, attempt=None):
    metadata = {}
    if safe_error_code is not None:
        metadata["safe_error_code"] = safe_error_code
    if attempt is not None:
        metadata["attempt"] = attempt
    action = {
        AuditOutcome.SUCCEEDED: "issuance.result_download_granted",
        AuditOutcome.DENIED: "issuance.result_download_denied",
        AuditOutcome.FAILED: "issuance.result_download_failed",
    }[outcome]
    record_event(actor, action, target, outcome, uuid.uuid4(), metadata)


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
        data = serializer.validated_data
        recipient_id = data.get("recipient_id")
        if not recipient_id and data.get("recipient_email"):
            recipient = resolve_recipient_for_issue(
                organization=request.user.organization,
                recipient_email=data["recipient_email"],
                recipient_name=data.get("recipient_name"),
            )
            recipient_id = recipient.id
        try:
            issuance, job = create_issuance(
                request.user,
                recipient_id=recipient_id,
                upload_id=data["upload_id"],
                correlation_id=data["correlation_id"],
            )
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


@method_decorator(never_cache, name="dispatch")
class IssuanceManifestView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [AccountRateThrottle, SourceIPRateThrottle]

    @issuance_manifest_schema
    def get(self, request, id):
        try:
            record = get_issuance(request.user, id)
        except WorkflowNotFound:
            _manifest_audit(
                request.user,
                request.user,
                AuditOutcome.DENIED,
                safe_error_code="WORKFLOW_NOT_FOUND",
            )
            raise Http404
        manifest = getattr(record, "manifest", None)
        if manifest is None:
            _manifest_audit(
                request.user,
                record,
                AuditOutcome.DENIED,
                safe_error_code="MANIFEST_UNAVAILABLE",
            )
            return Response({"code": "MANIFEST_UNAVAILABLE"}, status=409)
        try:
            projection = shareable_public_manifest(manifest)
        except DjangoValidationError:
            _manifest_audit(
                request.user,
                record,
                AuditOutcome.FAILED,
                safe_error_code="MANIFEST_NOT_SHAREABLE",
            )
            return Response({"code": "MANIFEST_NOT_SHAREABLE"}, status=409)
        _manifest_audit(request.user, record, AuditOutcome.SUCCEEDED)
        return Response(projection)


@method_decorator(never_cache, name="dispatch")
class IssuanceResultView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [AccountRateThrottle, SourceIPRateThrottle]

    @issuance_result_schema
    def get(self, request, id):
        try:
            record = get_issuance(request.user, id)
        except WorkflowNotFound:
            _result_download_audit(
                request.user,
                request.user,
                AuditOutcome.DENIED,
                safe_error_code="WORKFLOW_NOT_FOUND",
            )
            raise Http404
        evidence = issuance_result_evidence(record)
        if evidence is None:
            _result_download_audit(
                request.user,
                record,
                AuditOutcome.DENIED,
                safe_error_code="ISSUANCE_RESULT_UNAVAILABLE",
            )
            return Response({"code": "ISSUANCE_RESULT_UNAVAILABLE"}, status=409)
        expires_at = timezone.now() + ISSUANCE_RESULT_TTL
        try:
            download_url = get_storage().presign_get(
                key=evidence.output_object_key,
                expires=ISSUANCE_RESULT_TTL,
            )
        except StorageUnavailable:
            _result_download_audit(
                request.user,
                record,
                AuditOutcome.FAILED,
                safe_error_code="STORAGE_UNAVAILABLE",
            )
            return Response({"code": "STORAGE_UNAVAILABLE"}, status=503)
        except ValueError:
            _result_download_audit(
                request.user,
                record,
                AuditOutcome.DENIED,
                safe_error_code="ISSUANCE_RESULT_UNAVAILABLE",
            )
            return Response({"code": "ISSUANCE_RESULT_UNAVAILABLE"}, status=409)
        _result_download_audit(
            request.user,
            record,
            AuditOutcome.SUCCEEDED,
            attempt=evidence.attempt,
        )
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
