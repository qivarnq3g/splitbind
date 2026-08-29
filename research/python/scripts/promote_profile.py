"""Promote an exact complete SplitBind benchmark or record a factual no-release."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import tempfile


PYTHON_PROJECT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PYTHON_PROJECT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from splitbind_bench.promotion import (  # noqa: E402
    NoEligibleProfile,
    NonPromotableBenchmark,
    ensure_release_absent,
    load_benchmark_summary,
    promote_profile,
    write_evaluation_report,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Promote one fingerprint profile only from the exact complete A4 baseline."
    )
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--candidates", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        summary = load_benchmark_summary(arguments.summary, arguments.candidates)
    except NonPromotableBenchmark as error:
        if not _record_failed_promotion(error.evidence, arguments.output, arguments.report):
            return 2
        print(str(error), file=sys.stderr)
        return 4
    except (OSError, TypeError, ValueError) as error:
        _remove_failed_release(arguments.output)
        print(f"promotion rejected: {error}", file=sys.stderr)
        return 2
    output = arguments.output.absolute()
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=f".{output.name}.", dir=output.parent) as scope:
            staged_path = Path(scope) / output.name
            staged = promote_profile(summary, arguments.candidates, staged_path)
            released = replace(staged, destination=output)
            _preflight_release(staged_path, output)
            write_evaluation_report(summary, arguments.report, released)
            _publish_staged_release(staged_path, output)
    except NoEligibleProfile as error:
        _remove_failed_release(output)
        try:
            write_evaluation_report(summary, arguments.report, None)
        except (OSError, TypeError, ValueError) as report_error:
            print(f"promotion rejected: {report_error}", file=sys.stderr)
            return 2
        print(str(error), file=sys.stderr)
        return 3
    except (OSError, TypeError, ValueError) as error:
        _remove_failed_release(output)
        _remove_failed_report(arguments.report)
        print(f"promotion rejected: {error}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": "released",
                "profile_id": released.profile_id,
                "candidate_id": released.candidate_id,
                "output": str(released.destination),
                "sha256": released.document_sha256,
            },
            sort_keys=True,
        )
    )
    return 0


def _record_failed_promotion(summary, output: Path, report: Path) -> bool:
    _remove_failed_release(output)
    try:
        write_evaluation_report(summary, report, None)
    except (OSError, TypeError, ValueError) as error:
        _remove_failed_release(output)
        print(f"promotion rejected: {error}", file=sys.stderr)
        return False
    return True


def _remove_failed_release(output: Path) -> None:
    try:
        ensure_release_absent(output)
    except (OSError, TypeError, ValueError) as error:
        print(f"unable to remove exact release destination: {error}", file=sys.stderr)


def _remove_failed_report(report: Path) -> None:
    destination = report.absolute()
    if destination.exists() or destination.is_symlink():
        if destination.is_file() or destination.is_symlink():
            destination.unlink()


def _preflight_release(staged: Path, output: Path) -> None:
    if output.is_symlink():
        raise FileExistsError("release destination is a symlink")
    if output.exists():
        if not output.is_file():
            raise IsADirectoryError(f"release destination is not a file: {output}")
        if output.read_bytes() != staged.read_bytes():
            raise FileExistsError(
                "release destination already exists with different bytes; use an explicit new version"
            )


def _publish_staged_release(staged: Path, output: Path) -> None:
    _preflight_release(staged, output)
    if output.exists():
        staged.unlink()
    else:
        os.replace(staged, output)


if __name__ == "__main__":
    raise SystemExit(main())
