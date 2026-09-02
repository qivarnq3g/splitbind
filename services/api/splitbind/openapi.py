"""Explicit browser-facing OpenAPI contracts."""

from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_serializer,
)
from rest_framework import serializers

from splitbind.access.models import Role
from splitbind.access.serializers import LoginSerializer
from splitbind.documents.models import VerificationStatus
from splitbind.documents.serializers import IssuanceCreateSerializer, VerificationCreateSerializer
from splitbind.jobs.models import JobKind, JobStatus
from splitbind.jobs.serializers import CancelJobSerializer
from splitbind.uploads.serializers import UploadCompleteSerializer, UploadIntentSerializer


class SessionUserSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    username = serializers.CharField()
    role = serializers.ChoiceField(choices=Role.values)
    organization_id = serializers.UUIDField()


class SessionResponseSerializer(serializers.Serializer):
    authenticated = serializers.BooleanField()
    csrf_token = serializers.CharField()
    user = SessionUserSerializer(required=False)


class DetailErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()


class CodeErrorSerializer(serializers.Serializer):
    code = serializers.CharField()


VALIDATION_ERROR_SCHEMA = {
    "type": "object",
    "additionalProperties": {"type": "array", "items": {"type": "string"}},
}


class AuditEventSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    actor_id = serializers.UUIDField(allow_null=True)
    action = serializers.CharField()
    target_type = serializers.CharField()
    target_id = serializers.CharField()
    correlation_id = serializers.UUIDField()
    outcome = serializers.CharField()
    metadata = serializers.JSONField()
    created_at = serializers.DateTimeField()


class AuditEventListSerializer(serializers.Serializer):
    results = AuditEventSerializer(many=True)


class UploadSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    object_key = serializers.CharField()
    expected_sha256 = serializers.RegexField(r"^[0-9a-f]{64}$")
    size_bytes = serializers.IntegerField(min_value=1)
    expires_at = serializers.DateTimeField()
    finalized_at = serializers.DateTimeField(allow_null=True)


@extend_schema_serializer(component_name="UploadIntent")
class UploadIntentResponseSerializer(UploadSerializer):
    upload_url = serializers.URLField()
    required_headers = serializers.DictField(child=serializers.CharField())


class IssuanceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    job_id = serializers.UUIDField(allow_null=True)
    status = serializers.ChoiceField(choices=JobStatus.values, allow_null=True)
    issued_at = serializers.DateTimeField()


class SuspiciousRegionSerializer(serializers.Serializer):
    x = serializers.FloatField(min_value=0, max_value=1)
    y = serializers.FloatField(min_value=0, max_value=1)
    width = serializers.FloatField(min_value=0, max_value=1)
    height = serializers.FloatField(min_value=0, max_value=1)


class VerificationEvidenceSerializer(serializers.Serializer):
    fingerprint_confidence = serializers.FloatField(min_value=0, max_value=1, required=False)
    integrity_score = serializers.FloatField(min_value=0, max_value=1, allow_null=True, required=False)
    valid_vote_count = serializers.IntegerField(min_value=0, required=False)
    analyzed_page_count = serializers.IntegerField(min_value=0, required=False)
    manifest_signature_valid = serializers.BooleanField(allow_null=True, required=False)
    exact_file_hash_match = serializers.BooleanField(allow_null=True, required=False)
    suspicious_regions = SuspiciousRegionSerializer(many=True, required=False)
    limitations = serializers.ListField(child=serializers.CharField(), required=False)


class VerificationMetricsSerializer(serializers.Serializer):
    processing_ms = serializers.IntegerField(min_value=0, required=False)
    pages_processed = serializers.IntegerField(min_value=0, required=False)
    peak_rss_bytes = serializers.IntegerField(min_value=0, required=False)
    temp_peak_bytes = serializers.IntegerField(min_value=0, required=False)
    cleanup_failures = serializers.IntegerField(min_value=0, required=False)


class VerificationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    job_id = serializers.UUIDField(allow_null=True)
    job_status = serializers.ChoiceField(choices=JobStatus.values, allow_null=True)
    status = serializers.ChoiceField(choices=VerificationStatus.values, allow_null=True)
    created_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField(allow_null=True)
    evidence = VerificationEvidenceSerializer()
    metrics = VerificationMetricsSerializer()


class JobSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=JobKind.values)
    status = serializers.ChoiceField(choices=JobStatus.values)
    attempt = serializers.IntegerField(min_value=0, max_value=2)
    issuance_id = serializers.UUIDField(allow_null=True)
    verification_id = serializers.UUIDField(allow_null=True)
    deadline_at = serializers.DateTimeField()
    cancel_requested_at = serializers.DateTimeField(allow_null=True)
    safe_error_code = serializers.CharField(allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class LiveSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["ok"])


class ReadinessSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["ready", "not_ready"])
    components = serializers.DictField(child=serializers.ChoiceField(choices=["up", "down"]))


class DemoProcessingLimitsSerializer(serializers.Serializer):
    max_pdf_pages = serializers.IntegerField(min_value=1)
    max_pdf_bytes = serializers.IntegerField(min_value=1)
    max_image_pixels = serializers.IntegerField(min_value=1)


class DemoCapabilitySerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    processing_limits = DemoProcessingLimitsSerializer()
    algorithm_label = serializers.ChoiceField(choices=["experimental_unreleased_fingerprint_v2"])


CSRF_HEADER = OpenApiParameter(
    name="X-CSRFToken",
    type=str,
    location=OpenApiParameter.HEADER,
    required=True,
    description="Decoded csrftoken cookie value required by Django on unsafe requests.",
)

DETAIL_403 = OpenApiResponse(DetailErrorSerializer, description="Authentication, permission, or CSRF denied.")
DETAIL_404 = OpenApiResponse(DetailErrorSerializer, description="Resource not found in the caller's scope.")
DETAIL_429 = OpenApiResponse(DetailErrorSerializer, description="Request throttled.")
CODE_409 = OpenApiResponse(CodeErrorSerializer, description="Workflow state or idempotency conflict.")
CODE_503 = OpenApiResponse(CodeErrorSerializer, description="Object storage is unavailable.")
VALIDATION_400 = OpenApiResponse(VALIDATION_ERROR_SCHEMA, description="Request validation failed.")


def _validation_or_code(description):
    return OpenApiResponse(
        {"oneOf": [VALIDATION_ERROR_SCHEMA, {"$ref": "#/components/schemas/CodeError"}]},
        description=description,
    )


session_schema = extend_schema(operation_id="auth_session", auth=[], responses={200: SessionResponseSerializer})
login_schema = extend_schema(
    operation_id="auth_login", auth=[], parameters=[CSRF_HEADER], request=LoginSerializer,
    responses={200: SessionResponseSerializer, 400: VALIDATION_400, 403: DETAIL_403},
)
logout_schema = extend_schema(
    operation_id="auth_logout", parameters=[CSRF_HEADER], request=None,
    responses={200: SessionResponseSerializer, 403: DETAIL_403},
)
audit_list_schema = extend_schema(
    operation_id="audit_event_list", responses={200: AuditEventListSerializer, 403: DETAIL_403}
)
upload_intent_schema = extend_schema(
    operation_id="upload_intent_create", parameters=[CSRF_HEADER], request=UploadIntentSerializer,
    responses={
        201: UploadIntentResponseSerializer,
        400: _validation_or_code("Validation or safe upload error."),
        403: OpenApiResponse(
            {"oneOf": [{"$ref": "#/components/schemas/DetailError"}, {"$ref": "#/components/schemas/CodeError"}]},
            description="Authentication, permission, CSRF, or upload policy denied.",
        ),
        429: DETAIL_429,
        503: CODE_503,
    },
)
upload_complete_schema = extend_schema(
    operation_id="upload_complete", parameters=[CSRF_HEADER], request=UploadCompleteSerializer,
    responses={
        200: UploadSerializer,
        400: _validation_or_code("Validation or safe upload error."),
        403: DETAIL_403,
        404: DETAIL_404,
        429: DETAIL_429,
        503: CODE_503,
    },
)
issuance_create_schema = extend_schema(
    operation_id="issuance_create", parameters=[CSRF_HEADER], request=IssuanceCreateSerializer,
    responses={
        201: IssuanceSerializer,
        400: _validation_or_code("Validation or safe workflow error."),
        403: DETAIL_403,
        404: DETAIL_404,
        409: CODE_409,
        429: DETAIL_429,
    },
)
issuance_detail_schema = extend_schema(
    operation_id="issuance_retrieve", responses={200: IssuanceSerializer, 403: DETAIL_403, 404: DETAIL_404}
)
verification_create_schema = extend_schema(
    operation_id="verification_create", parameters=[CSRF_HEADER], request=VerificationCreateSerializer,
    responses={
        201: VerificationSerializer,
        400: _validation_or_code("Validation or safe workflow error."),
        403: DETAIL_403,
        404: DETAIL_404,
        409: CODE_409,
        429: DETAIL_429,
    },
)
verification_detail_schema = extend_schema(
    operation_id="verification_retrieve",
    responses={200: VerificationSerializer, 403: DETAIL_403, 404: DETAIL_404},
)
job_detail_schema = extend_schema(
    operation_id="job_retrieve", responses={200: JobSerializer, 403: DETAIL_403, 404: DETAIL_404}
)
job_cancel_schema = extend_schema(
    operation_id="job_cancel", parameters=[CSRF_HEADER], request=CancelJobSerializer,
    responses={200: JobSerializer, 400: VALIDATION_400, 403: DETAIL_403, 404: DETAIL_404, 409: CODE_409, 429: DETAIL_429},
)
live_schema = extend_schema(operation_id="health_live", auth=[], responses={200: LiveSerializer})
ready_schema = extend_schema(
    operation_id="health_ready", auth=[], responses={200: ReadinessSerializer, 503: ReadinessSerializer}
)
demo_capability_schema = extend_schema(
    operation_id="demo_capabilities_retrieve",
    responses={200: DemoCapabilitySerializer, 403: DETAIL_403},
)
