"""Run the independent SplitBind integrity-only tamper benchmark."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path


PYTHON_PROJECT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PYTHON_PROJECT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from splitbind_bench.integrity_runner import run_integrity_matrix  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Measure semi-fragile integrity localization without a fingerprint profile."
    )
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--evaluation", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    raw_arguments = list(sys.argv[1:] if argv is None else argv)
    arguments = _parser().parse_args(raw_arguments)
    command = "python research/python/scripts/run_integrity_benchmark.py " + " ".join(
        shlex.quote(value) for value in raw_arguments
    )
    summary = run_integrity_matrix(
        arguments.corpus,
        arguments.profile,
        arguments.matrix,
        arguments.seed,
        arguments.output,
        arguments.evaluation,
        command=command,
    )
    printable = {key: value for key, value in summary.items() if key != "rows"}
    print(json.dumps(printable, sort_keys=True))
    return 0 if summary["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
