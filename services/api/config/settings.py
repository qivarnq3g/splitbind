import os
from urllib.parse import unquote, urlparse

from .settings_common import *  # noqa: F403


def _required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Required production setting {name} is missing")
    return value


SECRET_KEY = _required_environment("DJANGO_SECRET_KEY")

_database_url = urlparse(_required_environment("DATABASE_URL"))
if _database_url.scheme not in {"postgres", "postgresql"}:
    raise RuntimeError("DATABASE_URL must use the postgresql scheme")
if not all([_database_url.hostname, _database_url.path.lstrip("/"), _database_url.username]):
    raise RuntimeError("DATABASE_URL must include PostgreSQL host, database, and user")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _database_url.path.lstrip("/"),
        "USER": unquote(_database_url.username),
        "PASSWORD": unquote(_database_url.password or ""),
        "HOST": os.environ.get("SPLITBIND_DATABASE_HOST", _database_url.hostname),
        "PORT": str(_database_url.port or 5432),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
    }
}
