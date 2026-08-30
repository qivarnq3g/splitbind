from django.http import JsonResponse
from django.views.decorators.http import require_GET

from splitbind.health.readiness import readiness


@require_GET
def live(request):
    return JsonResponse({"status": "ok"})


@require_GET
def ready(request):
    payload, status = readiness()
    return JsonResponse(payload, status=status)
