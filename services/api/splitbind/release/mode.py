from enum import StrEnum

from django.core.exceptions import ImproperlyConfigured


class ReleaseMode(StrEnum):
    INTEGRITY_V1 = "integrity_v1"


def load_release_mode(environment: str, value: object) -> ReleaseMode | None:
    """Load the explicitly selected production release without fallback modes."""
    if value is None:
        if environment == "production":
            raise ImproperlyConfigured(
                "SPLITBIND_RELEASE_MODE must be integrity_v1 in production"
            )
        return None
    if value != ReleaseMode.INTEGRITY_V1.value:
        raise ImproperlyConfigured(
            "SPLITBIND_RELEASE_MODE must be exactly integrity_v1"
        )
    return ReleaseMode.INTEGRITY_V1


def integrity_release_enabled(value: object) -> bool:
    return value is ReleaseMode.INTEGRITY_V1 or value == ReleaseMode.INTEGRITY_V1.value
