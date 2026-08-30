from django.http import JsonResponse


def csrf_failure(request, reason=""):
    del request, reason
    return JsonResponse({"detail": "CSRF validation failed."}, status=403)
