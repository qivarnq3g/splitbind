"""Access to the committed SplitBind algorithm contracts."""

from __future__ import annotations

import json
import os
from functools import cache
from pathlib import Path
from typing import Any


CONTRACT_ROOT_ENV = "SPLITBIND_ALGORITHM_CONTRACTS"


@cache
def payload_profile() -> dict[str, Any]:
    """Load the frozen version-1 payload profile."""

    return _load_algorithm_contract("payload-profile.v1.json")


@cache
def fingerprint_candidates() -> dict[str, Any]:
    """Load the frozen version-1 fingerprint candidate grid."""

    return _load_algorithm_contract("fingerprint-candidates.v1.json")


def _load_algorithm_contract(filename: str) -> dict[str, Any]:
    contract_path = _algorithm_contracts_root() / filename
    try:
        stream = contract_path.open(encoding="utf-8")
    except OSError as error:
        raise RuntimeError(
            f"unable to read SplitBind algorithm contract {contract_path}; "
            f"set {CONTRACT_ROOT_ENV} to the directory containing the A1 algorithm JSON files"
        ) from error
    with stream:
        return json.load(stream)


def _algorithm_contracts_root() -> Path:
    configured = os.environ.get(CONTRACT_ROOT_ENV)
    if configured is not None:
        root = Path(configured).expanduser().resolve()
        if root.is_dir():
            return root
        raise RuntimeError(
            f"{CONTRACT_ROOT_ENV} points to missing or non-directory path {root}; "
            "set it to the directory containing the A1 algorithm JSON files"
        )

    for ancestor in Path(__file__).resolve().parents:
        checkout_root = ancestor / "contracts" / "algorithm"
        if checkout_root.is_dir():
            return checkout_root
    raise RuntimeError(
        "SplitBind A1 algorithm contracts were not found beside this checkout; "
        f"set {CONTRACT_ROOT_ENV} to the directory containing the A1 algorithm JSON files"
    )
