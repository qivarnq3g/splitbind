import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured


if os.environ.get("ENVIRONMENT") != "local":
    raise ImproperlyConfigured(
        "local presentation settings require ENVIRONMENT=local"
    )
if os.environ.get("SPLITBIND_DEMO_MODE") != "true":
    raise ImproperlyConfigured(
        "local presentation settings require SPLITBIND_DEMO_MODE=true"
    )

from .settings_common import *  # noqa: E402,F403


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY is required")

PROJECT_ROOT = BASE_DIR.parents[1]  # noqa: F405
DEMO_ROOT = (PROJECT_ROOT / "artifacts" / "demo").resolve()
database_value = os.environ.get("SPLITBIND_DEMO_DATABASE_PATH", "")
if not database_value:
    raise ImproperlyConfigured("SPLITBIND_DEMO_DATABASE_PATH is required")
database_path = Path(database_value)
if not database_path.is_absolute():
    raise ImproperlyConfigured("SPLITBIND_DEMO_DATABASE_PATH must be absolute")
database_path = database_path.resolve()
if not database_path.is_relative_to(DEMO_ROOT):
    raise ImproperlyConfigured(
        "SPLITBIND_DEMO_DATABASE_PATH must stay inside artifacts/demo"
    )

ENVIRONMENT = "local"
SPLITBIND_DEMO_MODE = True
DEBUG = False
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(database_path),
    }
}
OBJECT_STORAGE_ENDPOINT = os.environ.get("OBJECT_STORAGE_ENDPOINT", "")
OBJECT_STORAGE_ENDPOINT_HINT = ""
OBJECT_STORAGE_BUCKET = os.environ.get("OBJECT_STORAGE_BUCKET", "")
OBJECT_STORAGE_ACCESS_KEY = os.environ.get("OBJECT_STORAGE_ACCESS_KEY", "")
OBJECT_STORAGE_SECRET_KEY = os.environ.get("OBJECT_STORAGE_SECRET_KEY", "")
