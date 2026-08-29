"""Deterministic integrity-only tamper measurement and factual reporting."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Mapping

import numpy as np

from splitbind_attack.attacks import AttackCase, apply_attack
from splitbind_bench.metrics import compute_localization_iou
from splitbind_bench.runner import iter_corpus_pages
from splitbind_ref.integrity import embed_integrity, verify_integrity


_KEY_DOMAIN = b"splitbind-integrity-benchmark-key-v1\x00"
_NONCE_DOMAIN = b"splitbind-integrity-benchmark-nonce-v1\x00"
_CASE_DOMAIN = b"splitbind-integrity-benchmark-case-v1\x00"


def run_integrity_matrix(
    corpus: str | Path,
    profile: str | Path,
    matrix: str | Path,
    seed: int,
    output_dir: str | Path,
    evaluation_path: str | Path,
    *,
    command: str,
) -> dict[str, object]:
    """Measure every tamper over non-negative corpus pages without fingerprint input."""

    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**64:
        raise ValueError("seed must be an unsigned 64-bit integer")
    if not isinstance(command, str) or not command.strip() or len(command) > 4096:
        raise ValueError("command must be a non-empty bounded string")
    corpus_path = Path(corpus).resolve()
    profile_path = Path(profile).resolve()
    matrix_path = Path(matrix).resolve()
    destination = Path(output_dir).resolve()
    evaluation = Path(evaluation_path).resolve()
    corpus_document = _load_json(corpus_path)
    profile_document = _load_json(profile_path)
    matrix_document = _load_json(matrix_path)
    fixture_ids = {
        str(entry["fixture_id"])
        for entry in _list(corpus_document, "entries")
        if isinstance(entry, Mapping) and entry.get("kind") != "negative_external"
    }
    tamper_cases = _tamper_cases(matrix_document)
    if not fixture_ids:
        raise ValueError("integrity benchmark corpus has no eligible sources")
    if not tamper_cases:
        raise ValueError("integrity benchmark matrix has no tamper cases")

    rows: list[dict[str, object]] = []
    limitation_counts: Counter[str] = Counter()
    failure_messages: list[str] = []
    seed_bytes = seed.to_bytes(8, "big")
    profile_sha256 = _sha256_file(profile_path)
    for page in iter_corpus_pages(corpus_path, fixture_ids=fixture_ids):
        context = (
            seed_bytes
            + page.source.fixture_id.encode("utf-8")
            + b"\x00"
            + page.page_index.to_bytes(4, "big")
            + bytes.fromhex(profile_sha256)
        )
        key = hashlib.sha256(_KEY_DOMAIN + context).digest()
        nonce = hashlib.sha256(_NONCE_DOMAIN + context).digest()[:16]
        try:
            embedded = embed_integrity(page.image, key, nonce, profile_document)
        except Exception as error:  # benchmark retains row-level execution failures
            for attack in tamper_cases:
                message = f"{type(error).__name__}: {error}"
                failure_messages.append(
                    f"{page.source.fixture_id}/p{page.page_index}/{attack.case_id}: {message}"
                )
                rows.append(
                    _failure_row(page.source.fixture_id, page.page_index, attack, message)
                )
            continue
        for attack in tamper_cases:
            case_seed = int.from_bytes(
                hashlib.sha256(
                    _CASE_DOMAIN + context + b"\x00" + attack.case_id.encode("utf-8")
                ).digest()[:8],
                "big",
            )
            try:
                artifact = apply_attack(
                    embedded.image, attack, np.random.default_rng(case_seed)
                )
                decision = verify_integrity(
                    artifact.image, key, nonce, profile_document
                )
                limitations = list(decision.limitations)
                limitation_counts.update(limitations)
                measured_iou = compute_localization_iou(
                    artifact.ground_truth, decision.suspicious_regions
                )
                aggregate_iou = measured_iou if not limitations else 0.0
                rows.append(
                    {
                        "fixture_id": page.source.fixture_id,
                        "page_index": page.page_index,
                        "tamper_id": attack.case_id,
                        "tamper_kind": str(attack.parameters["kind"]),
                        "iou": aggregate_iou,
                        "measured_iou": measured_iou,
                        "ground_truth": [
                            region.as_dict() for region in artifact.ground_truth
                        ],
                        "suspicious_regions": [
                            region.as_dict() for region in decision.suspicious_regions
                        ],
                        "evaluated_regions": decision.evaluated_regions,
                        "limitations": limitations,
                        "failure": None,
                    }
                )
            except Exception as error:  # benchmark retains row-level execution failures
                message = f"{type(error).__name__}: {error}"
                failure_messages.append(
                    f"{page.source.fixture_id}/p{page.page_index}/{attack.case_id}: {message}"
                )
                rows.append(
                    _failure_row(page.source.fixture_id, page.page_index, attack, message)
                )

    scheduled = len(rows)
    if scheduled == 0:
        raise RuntimeError("integrity benchmark scheduled no rows")
    failed = sum(row["failure"] is not None for row in rows)
    limited = sum(bool(row["limitations"]) for row in rows)
    per_tamper = []
    for attack in tamper_cases:
        attack_rows = [row for row in rows if row["tamper_id"] == attack.case_id]
        per_tamper.append(
            {
                "tamper_id": attack.case_id,
                "tamper_kind": str(attack.parameters["kind"]),
                "scheduled_cases": len(attack_rows),
                "aggregate_iou_denominator": len(attack_rows),
                "aggregate_iou": sum(float(row["iou"]) for row in attack_rows)
                / len(attack_rows),
                "failed_cases": sum(row["failure"] is not None for row in attack_rows),
                "limited_cases": sum(bool(row["limitations"]) for row in attack_rows),
            }
        )
    summary: dict[str, object] = {
        "schema_version": 1,
        "status": "complete" if failed == 0 else "complete_with_errors",
        "seed": seed,
        "command": command,
        "corpus_sha256": _sha256_file(corpus_path),
        "profile_sha256": profile_sha256,
        "matrix_sha256": _sha256_file(matrix_path),
        "corpus_pages": len({(row["fixture_id"], row["page_index"]) for row in rows}),
        "tamper_case_count": len(tamper_cases),
        "scheduled_tamper_cases": scheduled,
        "aggregate_iou_denominator": scheduled,
        "aggregate_iou": sum(float(row["iou"]) for row in rows) / scheduled,
        "failed_cases": failed,
        "limited_cases": limited,
        "limitations": dict(sorted(limitation_counts.items())),
        "failures": failure_messages,
        "per_tamper": per_tamper,
        "rows": rows,
    }
    destination.mkdir(parents=True, exist_ok=True)
    _atomic_write(
        destination / "summary.json",
        json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )
    evaluation.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(evaluation, _evaluation_markdown(summary))
    return summary


def _tamper_cases(document: Mapping[str, object]) -> tuple[AttackCase, ...]:
    cases = []
    for index, entry in enumerate(_list(document, "tamper")):
        if not isinstance(entry, Mapping):
            raise ValueError("tamper matrix entries must be mappings")
        kind = entry.get("kind")
        region = entry.get("region")
        if not isinstance(kind, str) or not isinstance(region, Mapping):
            raise ValueError("tamper matrix entry must contain kind and region")
        cases.append(
            AttackCase(
                case_id=f"tamper-{index:02d}-{kind}",
                kind="tamper",
                parameters={"kind": kind, "region": dict(region)},
            )
        )
    return tuple(cases)


def _failure_row(
    fixture_id: str, page_index: int, attack: AttackCase, message: str
) -> dict[str, object]:
    return {
        "fixture_id": fixture_id,
        "page_index": page_index,
        "tamper_id": attack.case_id,
        "tamper_kind": str(attack.parameters["kind"]),
        "iou": 0.0,
        "measured_iou": None,
        "ground_truth": [],
        "suspicious_regions": [],
        "evaluated_regions": 0,
        "limitations": [],
        "failure": message,
    }


def _evaluation_markdown(summary: Mapping[str, object]) -> str:
    lines = [
        "# SplitBind integrity profile v1 factual evaluation",
        "",
        "## Scope and binding limitation",
        "",
        "This is an integrity-only measurement over the versioned synthetic corpus and tamper matrix. "
        "It does not require, create, or synthesize `fingerprint-profile.v1.json`. The combined "
        "fingerprint-plus-integrity interaction benchmark remains deferred until a fingerprint "
        "profile legitimately passes Gate G1; A7 remains blocked.",
        "",
        "Localization IoU is research evidence, not a fingerprint release gate. Limited and failed "
        "rows contribute zero to the all-scheduled aggregate; poor results are preserved.",
        "",
        "## Reproduction",
        "",
        "```text",
        str(summary["command"]),
        "```",
        "",
        f"- Seed: `{summary['seed']}`",
        f"- Corpus SHA-256: `{summary['corpus_sha256']}`",
        f"- Integrity profile SHA-256: `{summary['profile_sha256']}`",
        f"- Tamper matrix SHA-256: `{summary['matrix_sha256']}`",
        "",
        "## Observed result",
        "",
        f"- Status: `{summary['status']}`",
        f"- Corpus pages: {summary['corpus_pages']}",
        f"- Tamper definitions: {summary['tamper_case_count']}",
        f"- Scheduled denominator: {summary['scheduled_tamper_cases']}",
        f"- Aggregate Localization IoU (all scheduled): {float(summary['aggregate_iou']):.6f}",
        f"- Execution failures: {summary['failed_cases']}",
        f"- Limited/indeterminate rows: {summary['limited_cases']}",
        "",
        "| Tamper | Scheduled denominator | Aggregate IoU | Failures | Limited |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in summary["per_tamper"]:  # type: ignore[union-attr]
        lines.append(
            f"| `{row['tamper_kind']}` | {row['scheduled_cases']} | "
            f"{float(row['aggregate_iou']):.6f} | {row['failed_cases']} | {row['limited_cases']} |"
        )
    lines.extend(
        [
            "",
            "## Limitations and failures",
            "",
            "Stable limitation counts: `"
            + json.dumps(summary["limitations"], sort_keys=True)
            + "`.",
        ]
    )
    failures = summary["failures"]
    if failures:
        lines.extend(["", "Observed execution failures:"])
        lines.extend(f"- `{failure}`" for failure in failures)  # type: ignore[union-attr]
    else:
        lines.extend(["", "No execution failures were observed."])
    lines.extend(
        [
            "",
            "The research target is Localization IoU at least 0.50. This document reports the "
            "observed result without changing fixtures, tamper regions, denominators, or promotion gates.",
            "",
        ]
    )
    return "\n".join(lines)


def _load_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"unable to load benchmark JSON {path}") from error
    if not isinstance(value, dict):
        raise ValueError(f"benchmark JSON root must be an object: {path}")
    return value


def _list(value: Mapping[str, object], key: str) -> list[object]:
    result = value.get(key)
    if not isinstance(result, list):
        raise ValueError(f"benchmark field {key} must be a list")
    return result


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write(path: Path, content: str) -> None:
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
