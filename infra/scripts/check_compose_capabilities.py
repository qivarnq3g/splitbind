"""Preflight the Docker Compose options used by SplitBind static validation."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys


REQUIRED_OPTIONS = ("--format", "--no-env-resolution", "--no-path-resolution")


def missing_capabilities(help_text: str) -> tuple[str, ...]:
    return tuple(
        option
        for option in REQUIRED_OPTIONS
        if re.search(rf"(?m)^\s*{re.escape(option)}(?:\s|$)", help_text) is None
    )


def _read_help(help_file: pathlib.Path | None) -> tuple[str, int]:
    if help_file is not None:
        try:
            return help_file.read_text(encoding="utf-8"), 0
        except OSError as error:
            print(f"COMPOSE_CAPABILITY_IO_ERROR: {error}", file=sys.stderr)
            return "", 2
    try:
        result = subprocess.run(
            ["docker", "compose", "config", "--help"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        print(
            "COMPOSE_CAPABILITY_PROBE_FAILED: could not run "
            f"'docker compose config --help': {error}",
            file=sys.stderr,
        )
        return "", 2
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        print(
            "COMPOSE_CAPABILITY_PROBE_FAILED: "
            f"'docker compose config --help' exited {result.returncode}: {detail}",
            file=sys.stderr,
        )
        return "", 2
    return result.stdout, 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--help-file",
        type=pathlib.Path,
        help="validate captured help text instead of probing the installed CLI",
    )
    arguments = parser.parse_args()
    help_text, status = _read_help(arguments.help_file)
    if status:
        return status
    missing = missing_capabilities(help_text)
    if missing:
        print(
            "COMPOSE_CAPABILITY_MISSING: "
            f"{', '.join(missing)}; upgrade Docker Compose to a release whose "
            "'docker compose config --help' lists every required option",
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "schema_version": 1,
                "command": ["docker", "compose", "config"],
                "required_options": list(REQUIRED_OPTIONS),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
