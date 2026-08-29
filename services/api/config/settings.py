import os

from .database import parse_postgresql_url
from .settings_common import *  # noqa: F403


def _required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required production setting {name} is missing")
    return value


SECRET_KEY = _required_environment("DJANGO_SECRET_KEY")
# Storage is environment-backed. The adapter validates this complete set when
# direct-upload functionality is initialized, preserving independent database
# configuration validation during settings import.
SPLITBIND_STORAGE_ENDPOINT = os.environ.get("SPLITBIND_STORAGE_ENDPOINT", "")
SPLITBIND_STORAGE_BUCKET = os.environ.get("SPLITBIND_STORAGE_BUCKET", "")
SPLITBIND_STORAGE_ACCESS_KEY_ID = os.environ.get("SPLITBIND_STORAGE_ACCESS_KEY_ID", "")
SPLITBIND_STORAGE_SECRET_ACCESS_KEY = os.environ.get("SPLITBIND_STORAGE_SECRET_ACCESS_KEY", "")

if os.environ.get("SPLITBIND_DATABASE_HOST") is not None:
    raise RuntimeError("SPLITBIND_DATABASE_HOST is unsupported; use NEON_DATABASE_HOST only as a matching host hint")

_database = parse_postgresql_url(
    _required_environment("DATABASE_URL"),
    os.environ.get("NEON_DATABASE_HOST"),
)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _database.name,
        "USER": _database.user,
        "PASSWORD": _database.password,
        "HOST": _database.host,
        "PORT": _database.port,
        "OPTIONS": _database.options,
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }
}
