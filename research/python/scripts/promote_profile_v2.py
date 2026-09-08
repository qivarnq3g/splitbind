"""Promote an independently validated V2 benchmark, or record no release."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


PYTHON_PROJECT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PYTHON_PROJECT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from splitbind_bench.promotion_v2 import (  # noqa: E402
    DEFAULT_CORPUS,
    DEFAULT_MATRIX,
    run_v2_promotion_cli,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail-closed V2 profile promotion; writes a factual no-release report when selection is empty."
    )
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--profiles", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        code, message = run_v2_promotion_cli(
            summary=arguments.summary,
            profiles=arguments.profiles,
            selection=arguments.selection,
            corpus=arguments.corpus,
            matrix=arguments.matrix,
            output=arguments.output,
            report=arguments.report,
        )
    except Exception as error:
        print(f"promotion rejected: {error}", file=sys.stderr)
        return 2
    print(json.dumps({"status": message}, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
