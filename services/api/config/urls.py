from django.contrib import admin
from django.urls import path

from splitbind.access.views import AuditEventListView, LoginView, LogoutView, SessionView
from splitbind.demo.capabilities import capabilities
from splitbind.health.views import live, ready
from splitbind.documents.views import (
    IssuanceCreateView,
    IssuanceDetailView,
    IssuanceResultView,
    VerificationCreateView,
    VerificationDetailView,
)
from splitbind.jobs.views import JobCancelView, JobDetailView, JobListView
from splitbind.uploads.views import UploadCompleteView, UploadIntentView


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/live", live, name="health-live"),
    path("health/ready", ready, name="health-ready"),
    path("api/v1/auth/session", SessionView.as_view(), name="auth-session"),
    path("api/v1/auth/login", LoginView.as_view(), name="auth-login"),
    path("api/v1/auth/logout", LogoutView.as_view(), name="auth-logout"),
    path("api/v1/demo/capabilities", capabilities, name="demo-capabilities"),
    path("api/v1/audit-events", AuditEventListView.as_view(), name="audit-event-list"),
    path("api/v1/uploads", UploadIntentView.as_view(), name="upload-intent"),
    path("api/v1/uploads/<uuid:id>/complete", UploadCompleteView.as_view(), name="upload-complete"),
    path("api/v1/issuances", IssuanceCreateView.as_view(), name="issuance-create"),
    path("api/v1/issuances/<uuid:id>", IssuanceDetailView.as_view(), name="issuance-detail"),
    path("api/v1/issuances/<uuid:id>/result", IssuanceResultView.as_view(), name="issuance-result"),
    path("api/v1/verifications", VerificationCreateView.as_view(), name="verification-create"),
    path("api/v1/verifications/<uuid:id>", VerificationDetailView.as_view(), name="verification-detail"),
    path("api/v1/jobs", JobListView.as_view(), name="job-list"),
    path("api/v1/jobs/<uuid:id>", JobDetailView.as_view(), name="job-detail"),
    path("api/v1/jobs/<uuid:id>/cancel", JobCancelView.as_view(), name="job-cancel"),
]
