from contextlib import contextmanager
from contextvars import ContextVar


_deletion_evidence_write = ContextVar("deletion_evidence_write", default=False)
_cleanup_schedule_write = ContextVar("cleanup_schedule_write", default=False)


def deletion_evidence_write_allowed() -> bool:
    return _deletion_evidence_write.get()


@contextmanager
def _allow_deletion_evidence_write():
    token = _deletion_evidence_write.set(True)
    try:
        yield
    finally:
        _deletion_evidence_write.reset(token)


def cleanup_schedule_write_allowed() -> bool:
    return _cleanup_schedule_write.get()


@contextmanager
def _allow_cleanup_schedule_write():
    token = _cleanup_schedule_write.set(True)
    try:
        yield
    finally:
        _cleanup_schedule_write.reset(token)
