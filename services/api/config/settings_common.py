import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .limits import load_runtime_limits
from splitbind.release.mode import load_release_mode


BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = False
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("SPLITBIND_ALLOWED_HOSTS", "").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "splitbind.access.apps.AccessConfig",
    "splitbind.uploads.apps.UploadsConfig",
    "splitbind.documents.apps.DocumentsConfig",
    "splitbind.jobs.apps.JobsConfig",
    "splitbind.outbox.apps.OutboxConfig",
    "splitbind.audit.apps.AuditConfig",
    "splitbind.health.apps.HealthConfig",
    "splitbind.demo.apps.DemoConfig",
    "splitbind.release",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

AUTH_USER_MODEL = "access.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = True
CSRF_FAILURE_VIEW = "splitbind.access.csrf.csrf_failure"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("SPLITBIND_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
if not CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS = [
        f"https://{host.strip()}"
        for host in ALLOWED_HOSTS
        if host.strip() and host.strip() not in ("*", "localhost", "127.0.0.1", "api")
    ]
    if os.environ.get("ENVIRONMENT") != "production":
        CSRF_TRUSTED_ORIGINS.extend([
            "http://localhost:8080",
            "http://127.0.0.1:8080",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ])

ENVIRONMENT = os.environ.get("ENVIRONMENT", "production")


def load_demo_mode(environment: str, value: object) -> bool:
    if value is None:
        return False
    if value == "true":
        enabled = True
    elif value == "false":
        enabled = False
    else:
        raise ImproperlyConfigured("SPLITBIND_DEMO_MODE must be exactly true or false")
    if enabled and environment not in {"local", "offline"}:
        raise ImproperlyConfigured(
            "SPLITBIND_DEMO_MODE may be enabled only in local or offline environments"
        )
    return enabled


SPLITBIND_DEMO_MODE = load_demo_mode(ENVIRONMENT, os.environ.get("SPLITBIND_DEMO_MODE"))
SPLITBIND_RELEASE_MODE = load_release_mode(
    ENVIRONMENT, os.environ.get("SPLITBIND_RELEASE_MODE")
)
SPLITBIND_MANIFEST_SIGNING_KEY_FILE = os.environ.get(
    "SPLITBIND_MANIFEST_SIGNING_KEY_FILE"
)
SPLITBIND_MANIFEST_SIGNING_KEY_PASSPHRASE_FILE = os.environ.get(
    "SPLITBIND_MANIFEST_SIGNING_KEY_PASSPHRASE_FILE"
)
globals().update(load_runtime_limits(ENVIRONMENT, os.environ))
def load_fingerprint_capability(value: object) -> bool:
    if value is None or value == "false":
        return False
    if value != "true":
        raise ImproperlyConfigured(
            "SPLITBIND_FINGERPRINT_ENABLED must be exactly true or false"
        )
    return True


SPLITBIND_FINGERPRINT_ENABLED = load_fingerprint_capability(
    os.environ.get("SPLITBIND_FINGERPRINT_ENABLED")
)
SPLITBIND_BROKER_READINESS = None
BROKER_READINESS_TIMEOUT_SECONDS = 1.0

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
if LOG_LEVEL not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
    raise ImproperlyConfigured("LOG_LEVEL must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "keyvalue": {
            "format": "ts=%(asctime)s level=%(levelname)s logger=%(name)s %(message)s",
            "datefmt": "%Y-%m-%dT%H:%M:%S%z",
        }
    },
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "keyvalue",
        }
    },
    "root": {"handlers": ["stdout"], "level": "WARNING"},
    "loggers": {
        "splitbind": {"handlers": ["stdout"], "level": LOG_LEVEL, "propagate": False},
        "django": {"handlers": ["stdout"], "level": "INFO", "propagate": False},
        "django.request": {"handlers": ["stdout"], "level": "WARNING", "propagate": False},
        "django.db.backends": {"handlers": ["stdout"], "level": "WARNING", "propagate": False},
    },
}

REST_FRAMEWORK = {
    "NUM_PROXIES": 1,
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_RATES": {
        "account": os.environ.get("ACCOUNT_THROTTLE_RATE", "60/min"),
        "source_ip": os.environ.get("SOURCE_IP_THROTTLE_RATE", "120/min"),
        "issuance_job": os.environ.get("ISSUANCE_THROTTLE_RATE", "10/hour"),
        "verification_job": os.environ.get("VERIFICATION_THROTTLE_RATE", "10/hour"),
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "SplitBind API",
    "DESCRIPTION": "Browser-facing SplitBind control-plane contract.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_ADD_EXPLICIT_BLANK_NULL_CHOICE": True,
    "ENUM_NAME_OVERRIDES": {
        "RoleEnum": ["administrator", "issuer", "verifier", "auditor"],
        "JobStatusEnum": [
            "created", "queued", "processing", "retryable_failed",
            "succeeded", "failed", "dead_lettered", "cancelled",
        ],
        "VerificationStatusEnum": [
            "VERIFIED_INTACT", "SOURCE_IDENTIFIED_MODIFIED", "PARTIAL_EVIDENCE",
            "NO_WATERMARK", "INVALID_MANIFEST", "PROCESSING_FAILED",
        ],
        "JobKindEnum": ["issuance", "verification"],
        "HealthStatusEnum": ["ok"],
        "ReadinessStatusEnum": ["ready", "not_ready"],
        "ComponentStatusEnum": ["up", "down", "not_applicable"],
    },
}
