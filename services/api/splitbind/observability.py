from __future__ import annotations

import logging
import traceback


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def safe_traceback(error: BaseException) -> str:
    kind = f"{type(error).__module__}.{type(error).__qualname__}"
    frames = "".join(traceback.format_tb(error.__traceback__)).strip()
    if not frames:
        return kind
    return f"{kind}\n{frames}"


def log_swallowed(logger: logging.Logger, error: BaseException, **context: object) -> None:
    fields = " ".join(f"{key}={value}" for key, value in context.items())
    logger.error("%s traceback=%s", fields, safe_traceback(error))
