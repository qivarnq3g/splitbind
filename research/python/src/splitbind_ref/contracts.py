"""Access to the committed SplitBind algorithm contracts."""

from __future__ import annotations

import json
import os
from copy import deepcopy
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


def fingerprint_candidates_v2() -> dict[str, Any]:
    """Load a defensive copy of the strict version-2 fingerprint contract."""

    return deepcopy(_fingerprint_candidates_v2_cached()[0])


def fingerprint_candidates_v2_bytes() -> bytes:
    """Return the exact committed UTF-8 bytes of the version-2 contract."""

    return bytes(_fingerprint_candidates_v2_cached()[1])


def fingerprint_candidates_v3() -> dict[str, Any]:
    """Load a defensive copy of the strict version-3 fingerprint contract."""

    return deepcopy(_fingerprint_candidates_v3_cached()[0])


def fingerprint_candidates_v3_bytes() -> bytes:
    """Return the exact committed UTF-8 bytes of the version-3 contract."""

    return bytes(_fingerprint_candidates_v3_cached()[1])


@cache
def _fingerprint_candidates_v2_cached() -> tuple[dict[str, Any], bytes]:
    contract_path = _algorithm_contracts_root() / "fingerprint-candidates.v2.json"
    try:
        raw = contract_path.read_bytes()
    except OSError as error:
        raise RuntimeError(
            f"unable to read SplitBind algorithm contract {contract_path}; "
            f"set {CONTRACT_ROOT_ENV} to the directory containing the V2 algorithm JSON files"
        ) from error
    try:
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid V2 fingerprint candidate contract {contract_path}") from error
    if not isinstance(parsed, dict):
        raise ValueError("V2 fingerprint candidate contract must be a JSON object")
    return parsed, raw


@cache
def _fingerprint_candidates_v3_cached() -> tuple[dict[str, Any], bytes]:
    contract_path = _algorithm_contracts_root() / "fingerprint-candidates.v3.json"
    try:
        raw = contract_path.read_bytes()
    except OSError as error:
        raise RuntimeError(
            f"unable to read SplitBind algorithm contract {contract_path}; "
            f"set {CONTRACT_ROOT_ENV} to the directory containing the V3 algorithm JSON files"
        ) from error
    try:
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid V3 fingerprint candidate contract {contract_path}") from error
    if not isinstance(parsed, dict):
        raise ValueError("V3 fingerprint candidate contract must be a JSON object")
    return parsed, raw


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r} in V2 fingerprint candidate contract")
        result[key] = value
    return result


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
