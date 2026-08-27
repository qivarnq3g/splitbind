"""Access to the committed SplitBind algorithm contracts."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any


_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_ALGORITHM_CONTRACTS = _PROJECT_ROOT / "contracts" / "algorithm"


@cache
def payload_profile() -> dict[str, Any]:
    """Load the frozen version-1 payload profile."""

    return _load_algorithm_contract("payload-profile.v1.json")


@cache
def fingerprint_candidates() -> dict[str, Any]:
    """Load the frozen version-1 fingerprint candidate grid."""

    return _load_algorithm_contract("fingerprint-candidates.v1.json")


def _load_algorithm_contract(filename: str) -> dict[str, Any]:
    with (_ALGORITHM_CONTRACTS / filename).open(encoding="utf-8") as stream:
        return json.load(stream)
