from __future__ import annotations

import logging
import traceback


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def _rendered(error: BaseException) -> str:
    kind = f"{type(error).__module__}.{type(error).__qualname__}"
    frames = "".join(traceback.format_tb(error.__traceback__)).strip()
    if not frames:
        return kind
    return f"{kind}\n{frames}"


def safe_traceback(error: BaseException, *, depth: int = 4) -> str:
    parts: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and len(parts) < depth and id(current) not in seen:
        seen.add(id(current))
        parts.append(_rendered(current))
        current = current.__cause__ or current.__context__
    return "\ncaused by ".join(parts)


def log_swallowed(logger: logging.Logger, error: BaseException, **context: object) -> None:
    fields = " ".join(f"{key}={value}" for key, value in context.items())
    logger.error("%s traceback=%s", fields, safe_traceback(error))
