from django.contrib import admin
from django.urls import path

from splitbind.access.views import AuditEventListView, LoginView, LogoutView, SessionView
from splitbind.health.views import live


urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/live", live, name="health-live"),
    path("api/v1/auth/session", SessionView.as_view(), name="auth-session"),
    path("api/v1/auth/login", LoginView.as_view(), name="auth-login"),
    path("api/v1/auth/logout", LogoutView.as_view(), name="auth-logout"),
    path("api/v1/audit-events", AuditEventListView.as_view(), name="audit-event-list"),
]
