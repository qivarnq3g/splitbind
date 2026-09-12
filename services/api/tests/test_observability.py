import logging

from splitbind.observability import log_swallowed, safe_traceback


SECRET = "AKIA" + "EXAMPLE" + "RUNTIMEVALUE"


def _raise_with_secret(secret):
    raise RuntimeError(f"provider rejected the request: {secret}")


def _captured_error():
    try:
        _raise_with_secret(SECRET)
    except RuntimeError as error:
        return error
    raise AssertionError("the helper must raise")


def test_safe_traceback_names_the_type_and_frames_without_any_runtime_value():
    rendered = safe_traceback(_captured_error())

    assert "RuntimeError" in rendered
    assert "test_observability.py" in rendered
    assert "_raise_with_secret" in rendered
    assert "provider rejected the request" in rendered
    assert SECRET not in rendered


def test_safe_traceback_survives_an_exception_that_was_never_raised():
    assert safe_traceback(ValueError("never raised")) == "builtins.ValueError"
    assert "never raised" not in safe_traceback(ValueError("never raised"))


def test_log_swallowed_records_context_and_frames_at_error_level(caplog):
    logger = logging.getLogger("splitbind.test.observability")
    with caplog.at_level(logging.ERROR, logger="splitbind.test.observability"):
        log_swallowed(logger, _captured_error(), action="cycle", job="job-1")

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.levelno == logging.ERROR
    message = record.getMessage()
    assert "action=cycle" in message
    assert "job=job-1" in message
    assert "RuntimeError" in message
    assert SECRET not in message
