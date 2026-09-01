"""Run or inspect the deterministic SplitBind research benchmark matrix."""

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

from splitbind_bench.runner import build_execution_plan, run_matrix  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the versioned SplitBind attack matrix without promoting a candidate."
    )
    parser.add_argument("--profiles", required=True, type=Path)
    parser.add_argument("--candidate-selection", type=Path)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--max-rows", type=int)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--shard-count", type=int, default=1)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    arguments = parser.parse_args(argv)
    if arguments.plan_only:
        plan = build_execution_plan(
            arguments.corpus,
            arguments.profiles,
            arguments.matrix,
            arguments.seed,
            smoke=arguments.smoke,
            candidate_selection=arguments.candidate_selection,
        )
        print(
            json.dumps(
                {
                    "attack_count": plan.attack_count,
                    "candidate_count": plan.candidate_count,
                    "corpus_pages": plan.corpus_pages,
                    "planned_rows": plan.planned_rows,
                    "seed": plan.seed,
                    "smoke": plan.smoke,
                },
                sort_keys=True,
            )
        )
        return 0
    if arguments.output is None:
        parser.error("--output is required unless --plan-only is used")
    summary = run_matrix(
        arguments.corpus,
        arguments.profiles,
        arguments.matrix,
        arguments.seed,
        arguments.output,
        smoke=arguments.smoke,
        max_rows=arguments.max_rows,
        shard_index=arguments.shard_index,
        shard_count=arguments.shard_count,
        candidate_selection=arguments.candidate_selection,
    )
    document = asdict(summary)
    document["output_dir"] = str(summary.output_dir)
    print(json.dumps(document, sort_keys=True))
    return 0 if summary.status in {"complete", "complete_shard"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
