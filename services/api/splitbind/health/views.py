from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from splitbind.health.readiness import readiness
from splitbind.openapi import live_schema, ready_schema


@live_schema
@api_view(["GET"])
@permission_classes([AllowAny])
def live(request):
    return JsonResponse({"status": "ok"})


@ready_schema
@api_view(["GET"])
@permission_classes([AllowAny])
def ready(request):
    payload, status = readiness()
    return JsonResponse(payload, status=status)
