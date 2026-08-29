from django.urls import path

from splitbind.health.views import live


urlpatterns = [path("health/live", live, name="health-live")]
