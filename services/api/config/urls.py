from django.contrib import admin
from django.urls import path

from splitbind.access.views import AuditEventListView, LoginView, LogoutView, SessionView
from splitbind.health.views import live
from splitbind.documents.views import (
    IssuanceCreateView,
    IssuanceDetailView,
    VerificationCreateView,
    VerificationDetailView,
)
from splitbind.jobs.views import JobCancelView, JobDetailView
from splitbind.uploads.views import UploadCompleteView, UploadIntentView


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/live", live, name="health-live"),
    path("api/v1/auth/session", SessionView.as_view(), name="auth-session"),
    path("api/v1/auth/login", LoginView.as_view(), name="auth-login"),
    path("api/v1/auth/logout", LogoutView.as_view(), name="auth-logout"),
    path("api/v1/audit-events", AuditEventListView.as_view(), name="audit-event-list"),
    path("api/v1/uploads", UploadIntentView.as_view(), name="upload-intent"),
    path("api/v1/uploads/<uuid:upload_id>/complete", UploadCompleteView.as_view(), name="upload-complete"),
    path("api/v1/issuances", IssuanceCreateView.as_view(), name="issuance-create"),
    path("api/v1/issuances/<uuid:record_id>", IssuanceDetailView.as_view(), name="issuance-detail"),
    path("api/v1/verifications", VerificationCreateView.as_view(), name="verification-create"),
    path("api/v1/verifications/<uuid:record_id>", VerificationDetailView.as_view(), name="verification-detail"),
    path("api/v1/jobs/<uuid:job_id>", JobDetailView.as_view(), name="job-detail"),
    path("api/v1/jobs/<uuid:job_id>/cancel", JobCancelView.as_view(), name="job-cancel"),
]
