"""Validate a credential-free database DNS host for deployment preflight."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse


DNS_HOST = re.compile(
    r"(?=.{1,253}\Z)"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z",
    re.ASCII,
)


class DatabaseHostValidationError(ValueError):
    pass


def _validate_suffix(required_suffix: str) -> None:
    if not required_suffix.startswith(".") or DNS_HOST.fullmatch(
        f"suffix-check{required_suffix}"
    ) is None:
        raise DatabaseHostValidationError(
            "required suffix must be a lowercase DNS suffix beginning with '.'"
        )


def validate_database_host(value: str, required_suffix: str) -> str:
    """Return a validated host-only DNS name or raise a safe diagnostic."""

    _validate_suffix(required_suffix)
    if not value or any(
        character.isspace() or ord(character) < 32 or ord(character) == 127
        for character in value
    ):
        raise DatabaseHostValidationError(
            "database host must not contain whitespace or control characters"
        )
    try:
        authority = urllib.parse.urlsplit(f"//{value}")
        port = authority.port
    except ValueError as error:
        raise DatabaseHostValidationError(
            "database host is not a valid host-only authority"
        ) from error
    if authority.username is not None or authority.password is not None:
        raise DatabaseHostValidationError("database host must not contain credentials")
    if port is not None:
        raise DatabaseHostValidationError("database host must not contain a port")
    if authority.path or authority.query or authority.fragment:
        raise DatabaseHostValidationError(
            "database host must not contain a path, query, or fragment"
        )
    if authority.hostname is None or authority.hostname != value:
        raise DatabaseHostValidationError(
            "database host must contain only one lowercase DNS hostname"
        )
    if DNS_HOST.fullmatch(value) is None:
        raise DatabaseHostValidationError(
            "database host must match the lowercase ASCII DNS-host grammar"
        )
    if not value.endswith(required_suffix):
        raise DatabaseHostValidationError(
            f"database host must end with required suffix {required_suffix}"
        )
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-host", required=True)
    parser.add_argument("--required-suffix", required=True)
    arguments = parser.parse_args()
    try:
        database_host = validate_database_host(
            arguments.database_host,
            arguments.required_suffix,
        )
    except DatabaseHostValidationError as error:
        print(f"DATABASE_HOST_INVALID: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "schema_version": 1,
                "database_host": database_host,
                "required_suffix": arguments.required_suffix,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
