"""Promote an exact complete SplitBind benchmark or record a factual no-release."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


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
        released = promote_profile(summary, arguments.candidates, arguments.output)
    except NonPromotableBenchmark as error:
        ensure_release_absent(arguments.output)
        write_evaluation_report(error.evidence, arguments.report, None)
        print(str(error), file=sys.stderr)
        return 4
    except NoEligibleProfile as error:
        write_evaluation_report(summary, arguments.report, None)
        print(str(error), file=sys.stderr)
        return 3
    except (OSError, TypeError, ValueError) as error:
        print(f"promotion rejected: {error}", file=sys.stderr)
        return 2
    write_evaluation_report(summary, arguments.report, released)
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


if __name__ == "__main__":
    raise SystemExit(main())
