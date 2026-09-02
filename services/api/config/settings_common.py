import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .limits import load_runtime_limits


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
    if environment == "production" and enabled:
        raise ImproperlyConfigured("SPLITBIND_DEMO_MODE cannot be enabled in production")
    return enabled


SPLITBIND_DEMO_MODE = load_demo_mode(ENVIRONMENT, os.environ.get("SPLITBIND_DEMO_MODE"))
globals().update(load_runtime_limits(ENVIRONMENT, os.environ))
SPLITBIND_BROKER_READINESS = None
BROKER_READINESS_TIMEOUT_SECONDS = 1.0

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
    "ENUM_ADD_EXPLICIT_BLANK_NULL_CHOICE": False,
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
        "ComponentStatusEnum": ["up", "down"],
    },
}
