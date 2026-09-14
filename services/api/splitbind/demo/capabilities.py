from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from splitbind.openapi import demo_capability_schema
from splitbind.release.mode import integrity_release_enabled


DEMO_PROCESSING_LIMITS = {
    "max_pdf_pages": 5,
    "max_pdf_bytes": 10 * 1024 * 1024,
    "max_image_pixels": 40_000_000,
}
DEMO_ALGORITHM_LABEL = "experimental_unreleased_fingerprint_v2"


@demo_capability_schema
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def capabilities(request):
    integrity_mode = integrity_release_enabled(
        getattr(settings, "SPLITBIND_RELEASE_MODE", None)
    )
    payload = {
        "enabled": settings.SPLITBIND_DEMO_MODE or integrity_mode,
        "processing_limits": DEMO_PROCESSING_LIMITS,
        "algorithm_label": (
            "integrity_release_v1" if integrity_mode else DEMO_ALGORITHM_LABEL
        ),
    }
    if integrity_mode:
        fingerprint_enabled = bool(
            getattr(settings, "SPLITBIND_FINGERPRINT_ENABLED", False)
        )
        payload.update(
            hidden_fingerprint_enabled=fingerprint_enabled,
            transformed_attribution_available=fingerprint_enabled,
        )
    return Response(payload)
