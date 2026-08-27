#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]

COMMANDS = [
    {
        "name": "npm-ci",
        "argv": ["npm", "ci", "--ignore-scripts"],
    },
    {
        "name": "python-environment",
        "argv": [
            "{python}",
            "-m",
            "pip",
            "install",
            "-c",
            "research/python/constraints-py311.txt",
            "./research/python[test]",
        ],
    },
    {
        "name": "platform-tests",
        "argv": [
            "{python}",
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests/platform",
            "-p",
            "test_*.py",
            "-v",
        ],
    },
    {
        "name": "research-tests",
        "argv": [
            "{python}",
            "-m",
            "pytest",
            "research/python/tests",
            "-v",
        ],
    },
]


def _materialize(argv):
    materialized = [sys.executable if value == "{python}" else value for value in argv]
    executable = shutil.which(materialized[0])
    if executable is not None:
        materialized[0] = executable
    return materialized


def run_commands(commands):
    for command in commands:
        argv = _materialize(command["argv"])
        print(f"SMOKE_RUN:{command['name']}", flush=True)
        result = subprocess.run(argv, cwd=ROOT, check=False)
        if result.returncode != 0:
            return result.returncode
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.dry_run:
        json.dump({"schema_version": 1, "commands": COMMANDS}, sys.stdout)
        sys.stdout.write("\n")
        return 0
    return run_commands(COMMANDS)


if __name__ == "__main__":
    raise SystemExit(main())
