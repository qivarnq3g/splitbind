"""Run or independently verify the deterministic fingerprint V3 pre-gate."""

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

from splitbind_bench.pregate_v3 import (  # noqa: E402
    load_v3_pregate_summary,
    run_v3_pregate,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run or verify the bounded fingerprint V3 cost-control pre-gate."
    )
    parser.add_argument("--profiles", required=True, type=Path)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--matrix", type=Path)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--max-rows", type=int, help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.verify is not None:
        if arguments.smoke or arguments.output is not None or arguments.seed is not None:
            raise SystemExit("--verify cannot be combined with --smoke, --output, or --seed")
        keywords = {}
        if arguments.corpus is not None:
            keywords["corpus"] = arguments.corpus
        if arguments.matrix is not None:
            keywords["matrix"] = arguments.matrix
        summary = load_v3_pregate_summary(
            arguments.verify,
            arguments.profiles,
            **keywords,
        )
    else:
        missing = [
            name
            for name in ("corpus", "matrix", "seed", "output")
            if getattr(arguments, name) is None
        ]
        if missing:
            raise SystemExit("run mode requires --" + ", --".join(missing))
        summary = run_v3_pregate(
            arguments.corpus,
            arguments.profiles,
            arguments.matrix,
            arguments.seed,
            arguments.output,
            smoke=arguments.smoke,
            max_rows=arguments.max_rows,
        )
    print(json.dumps(asdict(summary), sort_keys=True))
    if arguments.smoke:
        return (
            0
            if summary.status == "complete"
            and summary.execution_errors == 0
            and summary.false_attributions == 0
            else 2
        )
    return (
        0
        if summary.status == "complete"
        and summary.execution_errors == 0
        and summary.false_attributions == 0
        and bool(summary.qualified_candidate_ids)
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
