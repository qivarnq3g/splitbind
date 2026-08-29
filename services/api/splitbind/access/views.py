import uuid

from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from splitbind.access.permissions import IsAdministratorOrAuditor
from splitbind.access.serializers import LoginSerializer, serialize_session_user
from splitbind.audit.models import AuditEvent, AuditOutcome
from splitbind.audit.services import record_event


def session_payload(request) -> dict[str, object]:
    payload: dict[str, object] = {
        "authenticated": bool(request.user.is_authenticated),
        "csrf_token": get_token(request),
    }
    if request.user.is_authenticated:
        payload["user"] = serialize_session_user(request.user)
    return payload


class SessionView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(session_payload(request))


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        django_login(request, user)
        record_event(
            actor=user,
            action="auth.login",
            target=user,
            outcome=AuditOutcome.SUCCEEDED,
            correlation_id=uuid.uuid4(),
            metadata={"kind": "login", "role": user.role},
        )
        return Response(session_payload(request))


@method_decorator(csrf_protect, name="dispatch")
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        record_event(
            actor=user,
            action="auth.logout",
            target=user,
            outcome=AuditOutcome.SUCCEEDED,
            correlation_id=uuid.uuid4(),
            metadata={"kind": "logout", "role": user.role},
        )
        django_logout(request)
        return Response(session_payload(request))


class AuditEventListView(APIView):
    permission_classes = [IsAuthenticated, IsAdministratorOrAuditor]

    def get(self, request):
        events = AuditEvent.objects.filter(organization_id=request.user.organization_id).order_by(
            "-created_at", "-id"
        )
        return Response(
            {
                "results": [
                    {
                        "id": str(event.id),
                        "actor_id": str(event.actor_id) if event.actor_id else None,
                        "action": event.action,
                        "target_type": event.target_type,
                        "target_id": event.target_id,
                        "correlation_id": str(event.correlation_id),
                        "outcome": event.outcome,
                        "metadata": event.metadata,
                        "created_at": event.created_at.isoformat(),
                    }
                    for event in events
                ]
            }
        )
