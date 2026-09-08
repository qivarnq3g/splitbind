from django.http import Http404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from splitbind.access.throttles import AccountRateThrottle, SourceIPRateThrottle
from splitbind.integrations.storage.base import UploadRejected
from splitbind.openapi import upload_complete_schema, upload_intent_schema
from splitbind.uploads.serializers import UploadCompleteSerializer, UploadIntentSerializer, serialize_upload
from splitbind.uploads.services import complete_upload, create_upload, record_serializer_denial


@method_decorator(csrf_protect, name="dispatch")
class UploadIntentView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [AccountRateThrottle, SourceIPRateThrottle]

    @upload_intent_schema
    def post(self, request):
        serializer = UploadIntentSerializer(data=request.data)
        if not serializer.is_valid():
            record_serializer_denial(request.user, action="upload.intent.denied", errors=serializer.errors)
            return Response(serializer.errors, status=400)
        try:
            intent = create_upload(request.user, **serializer.validated_data)
        except UploadRejected as error:
            code = str(error)
            status = 503 if code == "STORAGE_UNAVAILABLE" else 403 if code == "UPLOAD_FORBIDDEN" else 400
            return Response({"code": code}, status=status)
        return Response(
            serialize_upload(intent.record, upload_url=intent.url, required_headers=intent.required_headers), status=201
        )


@method_decorator(csrf_protect, name="dispatch")
class UploadCompleteView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [AccountRateThrottle, SourceIPRateThrottle]

    @upload_complete_schema
    def post(self, request, id):
        serializer = UploadCompleteSerializer(data=request.data)
        if not serializer.is_valid():
            record_serializer_denial(request.user, action="upload.complete.denied", errors=serializer.errors)
            return Response(serializer.errors, status=400)
        try:
            upload = complete_upload(request.user, upload_id=id, **serializer.validated_data)
        except UploadRejected as error:
            if str(error) == "UPLOAD_NOT_FOUND":
                raise Http404
            status = 503 if str(error) == "STORAGE_UNAVAILABLE" else 400
            return Response({"code": str(error)}, status=status)
        return Response(serialize_upload(upload))
