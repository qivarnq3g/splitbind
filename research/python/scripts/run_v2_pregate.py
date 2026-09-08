"""Run the exact deterministic fingerprint V2 qualification pre-gate."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path


PYTHON_PROJECT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PYTHON_PROJECT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from splitbind_bench.pregate_v2 import run_v2_pregate  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the exact 1,408-row fingerprint V2 cost-control pre-gate."
    )
    parser.add_argument("--profiles", required=True, type=Path)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--max-rows", type=int, help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    summary = run_v2_pregate(
        arguments.corpus,
        arguments.profiles,
        arguments.matrix,
        arguments.seed,
        arguments.output,
        max_rows=arguments.max_rows,
    )
    print(json.dumps(asdict(summary), sort_keys=True))
    return (
        0
        if summary.status == "complete"
        and summary.execution_errors == 0
        and bool(summary.qualified_candidate_ids)
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
