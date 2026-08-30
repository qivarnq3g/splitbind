from django.conf import settings
from django.db import connection
from django.db.models import Q
from django.utils import timezone

from splitbind.access.models import SigningKey, SigningKeyStatus, validate_ed25519_public_pem
from splitbind.integrations.storage.s3 import S3ObjectStorage


def database_ready() -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        return cursor.fetchone() == (1,)


def broker_ready() -> bool:
    probe = getattr(settings, "SPLITBIND_BROKER_READINESS", None)
    if not callable(probe):
        return False
    return probe(timeout_seconds=float(getattr(settings, "BROKER_READINESS_TIMEOUT_SECONDS", 1.0))) is True


def storage_configuration_ready() -> bool:
    S3ObjectStorage.validate_settings_configuration()
    return True


def public_key_registry_ready() -> bool:
    now = timezone.now()
    candidates = SigningKey.objects.filter(
        algorithm="Ed25519",
        status=SigningKeyStatus.ACTIVE,
        valid_from__lte=now,
    ).filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now))
    for key in candidates.order_by("key_id")[:20]:
        try:
            key.clean()
            validate_ed25519_public_pem(key.public_key)
            return True
        except Exception:
            continue
    return False


def readiness() -> tuple[dict[str, object], int]:
    checks = {
        "database": database_ready,
        "broker": broker_ready,
        "storage_config": storage_configuration_ready,
        "public_key_registry": public_key_registry_ready,
    }
    components = {}
    for name, check in checks.items():
        try:
            components[name] = "up" if check() else "down"
        except Exception:
            components[name] = "down"
    is_ready = all(value == "up" for value in components.values())
    return {
        "status": "ready" if is_ready else "not_ready",
        "components": components,
    }, 200 if is_ready else 503
