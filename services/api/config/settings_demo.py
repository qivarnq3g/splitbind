import os
import stat
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

PROJECT_ROOT = BASE_DIR.parents[1].resolve()  # noqa: F405
DEMO_ROOT = PROJECT_ROOT / "artifacts" / "demo"


def _is_reparse_point(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    return path.is_symlink() or bool(
        getattr(metadata, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _validate_contained_non_reparse_path(path: Path, root: Path) -> Path:
    if not path.is_absolute():
        raise ImproperlyConfigured("SPLITBIND_DEMO_DATABASE_PATH must be absolute")
    candidate = Path(os.path.abspath(path))
    try:
        relative = candidate.relative_to(root)
    except ValueError as error:
        raise ImproperlyConfigured(
            "SPLITBIND_DEMO_DATABASE_PATH must stay inside artifacts/demo"
        ) from error
    current = PROJECT_ROOT
    for component in Path("artifacts", "demo", *relative.parts).parts:
        current /= component
        if _is_reparse_point(current):
            raise ImproperlyConfigured(
                "SPLITBIND_DEMO_DATABASE_PATH cannot traverse a reparse point"
            )
        if not os.path.lexists(current):
            break
    return candidate


database_value = os.environ.get("SPLITBIND_DEMO_DATABASE_PATH", "")
if not database_value:
    raise ImproperlyConfigured("SPLITBIND_DEMO_DATABASE_PATH is required")
database_path = Path(database_value)
database_path = _validate_contained_non_reparse_path(database_path, DEMO_ROOT)

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
