import re
from collections.abc import Mapping

from django.core.exceptions import ImproperlyConfigured


SAFETY_CEILINGS = {
    "MAX_PDF_BYTES": 100 * 1024 * 1024,
    "MAX_PDF_PAGES": 50,
    "MAX_IMAGE_PIXELS": 40_000_000,
    "MAX_DOCUMENT_RASTER_PIXELS": 140_000_000,
    "JOB_TIMEOUT_SECONDS": 600,
    "WORKER_CONCURRENCY": 1,
    "RETENTION_RECONCILIATION_LEASE_SECONDS": 600,
}
RUNTIME_DEFAULTS = {
    "MAX_PDF_BYTES": 100 * 1024 * 1024,
    "MAX_PDF_PAGES": 50,
    "MAX_IMAGE_PIXELS": 40_000_000,
    "MAX_DOCUMENT_RASTER_PIXELS": 140_000_000,
    "JOB_TIMEOUT_SECONDS": 600,
    "WORKER_CONCURRENCY": 1,
    "RETENTION_RECONCILIATION_LEASE_SECONDS": 300,
}
_MAX_PARSED_INTEGER = 2_147_483_647


def parse_positive_decimal(name: str, value: object) -> int:
    if not isinstance(value, str) or re.fullmatch(r"[1-9][0-9]*", value) is None:
        raise ImproperlyConfigured(f"{name} must be a positive base-10 integer")
    parsed = int(value, 10)
    if parsed > _MAX_PARSED_INTEGER:
        raise ImproperlyConfigured(f"{name} exceeds the supported integer range")
    return parsed


def load_runtime_limits(environment: str, values: Mapping[str, object]) -> dict[str, int]:
    if environment not in {"production", "local", "offline", "test"}:
        raise ImproperlyConfigured("ENVIRONMENT must identify a supported runtime")
    result: dict[str, int] = {}
    for name, ceiling in SAFETY_CEILINGS.items():
        supplied = values.get(name)
        if supplied is None:
            if environment == "production":
                raise ImproperlyConfigured(f"{name} is required in production")
            result[name] = RUNTIME_DEFAULTS[name]
            continue
        parsed = parse_positive_decimal(name, supplied)
        if parsed > ceiling:
            raise ImproperlyConfigured(f"{name} exceeds safety ceiling {ceiling}")
        result[name] = parsed
    return result
