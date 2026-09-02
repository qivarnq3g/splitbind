from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from splitbind.openapi import demo_capability_schema


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
    return Response(
        {
            "enabled": settings.SPLITBIND_DEMO_MODE,
            "processing_limits": DEMO_PROCESSING_LIMITS,
            "algorithm_label": DEMO_ALGORITHM_LABEL,
        }
    )
