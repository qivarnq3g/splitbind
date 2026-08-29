"""Fail-closed promotion of a fully measured SplitBind fingerprint candidate."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import tempfile
from typing import Iterable, Mapping, Sequence
from uuid import UUID

from splitbind_attack.attacks import AttackCase
from splitbind_attack.ground_truth import NormalizedRect
from splitbind_bench.runner import (
    Candidate,
    ExecutionPlan,
    _benchmark_dimensions,
    _case_context,
    _remaining_embedded_tiles,
    build_execution_plan,
)


ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CORPUS = ROOT / "fixtures" / "corpus" / "corpus-manifest.v1.json"
DEFAULT_MATRIX = ROOT / "contracts" / "algorithm" / "attack-matrix.v1.json"
REQUIRED_SEED = 20260827
REQUIRED_CORPUS_PAGES = 22
REQUIRED_CANDIDATES = 48
REQUIRED_ATTACKS = 31
REQUIRED_ROWS = 32736
BASELINE_REQUIREMENTS_VERSION = 1
REQUIRED_CONTRACT_HASHES = {
    "corpus_sha256": "e5837cd446ab9c9959ba3fc4b85d205ec9d80e91efc6f801d139810b088a77ef",
    "profiles_sha256": "d3a8c2ec271c76a2ed424dd52fc5f2760ddd3ef2773663168bbad68e54865e9f",
    "attack_matrix_sha256": "fb3c485d45df15b5f16f76e888be0c2d443d2433ba35cdb1df06a85881a6d40e",
}
REQUIRED_PLAN_SHA256 = "9118eb9424e32400548d7feae4cb5d9c9c827359d9d8b74a6d9e3a9f0d7f71f3"
_IDENTITY_DOMAIN = b"splitbind-benchmark-identity-v1\x00"


@dataclass(frozen=True, slots=True)
class ProfileScore:
    profile_id: str
    candidate_id: str
    false_attribution: int
    execution_errors: int
    scheduled_rows: int
    jpeg70_true_attribution: int
    jpeg70_denominator: int
    jpeg70_rate: float
    resize075_true_attribution: int
    resize075_denominator: int
    resize075_rate: float
    crop025_true_attribution: int
    crop025_denominator: int
    crop025_rate: float
    quality_observations: int
    mean_psnr_db: float
    mean_ssim: float
    processing_observations: int
    processing_ms_per_page: float
    failed_gates: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BenchmarkSummary:
    schema_version: int
    status: str
    seed: int
    corpus_pages: int
    candidate_count: int
    attack_count: int
    planned_rows: int
    completed_rows: int
    execution_errors: int
    contract_hashes: Mapping[str, str]
    plan_sha256: str
    results_sha256: str
    source_summary_sha256: str
    profiles: tuple[ProfileScore, ...]
    limitations: tuple[str, ...]
    execution_error_details: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReleasedProfile:
    profile_id: str
    candidate_id: str
    destination: Path
    document_sha256: str


class NoEligibleProfile(RuntimeError):
    """Raised after validated evidence contains no candidate satisfying Gate G1."""


class NonPromotableBenchmark(ValueError):
    """A structurally complete benchmark is factual evidence but cannot promote."""

    def __init__(self, evidence: BenchmarkSummary):
        super().__init__(
            f"benchmark status {evidence.status} has "
            f"{evidence.execution_errors} execution errors"
        )
        self.evidence = evidence


def eligible_profiles(summary: BenchmarkSummary) -> tuple[ProfileScore, ...]:
    """Return candidates satisfying exact Gate G1, in deterministic rank order."""

    _require_complete_error_free_summary(summary)
    eligible = [
        score
        for score in summary.profiles
        if score.false_attribution == 0
        and score.execution_errors == 0
        and score.jpeg70_rate >= 0.95
        and score.resize075_rate >= 0.95
        and score.crop025_rate >= 0.90
        and score.mean_psnr_db >= 38.0
        and score.mean_ssim >= 0.95
    ]
    eligible.sort(
        key=lambda score: (
            -score.mean_ssim,
            -min(score.jpeg70_rate, score.resize075_rate, score.crop025_rate),
            score.processing_ms_per_page,
            score.profile_id,
        )
    )
    return tuple(eligible)


def aggregate_profile_scores(rows: Iterable[Mapping[str, object]]) -> tuple[ProfileScore, ...]:
    """Aggregate Gate G1 from measured rows, never from pre-aggregated fields.

    Detection-rate denominators are scheduled positive executions for the exact
    JPEG-70 and resize-0.75 attacks. Crop-0.25 uses only positive executions
    whose remaining-tile geometry is explicitly eligible. Quality has one
    unsigned-image observation per positive candidate/page before attack; the
    value repeated on attack rows must agree exactly. Processing time is the
    arithmetic mean attack-and-decode milliseconds per scheduled page row.
    """

    grouped: dict[str, list[Mapping[str, object]]] = {}
    for ordinal, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"result row {ordinal} must be an object")
        profile_id = _required_string(row, "algorithm_profile_sha256")
        grouped.setdefault(profile_id, []).append(row)

    scores = [_aggregate_one(profile_id, values) for profile_id, values in grouped.items()]
    scores.sort(key=lambda score: score.profile_id)
    return tuple(scores)


def load_benchmark_summary(
    summary: str | Path,
    candidates: str | Path,
    *,
    corpus: str | Path = DEFAULT_CORPUS,
    matrix: str | Path = DEFAULT_MATRIX,
) -> BenchmarkSummary:
    """Validate an exact full A4 run and independently reaggregate its JSONL."""

    summary_path = Path(summary).resolve()
    results_path = summary_path.with_name("results.jsonl")
    candidate_path = Path(candidates).resolve()
    plan = build_execution_plan(corpus, candidate_path, matrix, REQUIRED_SEED)
    _validate_required_plan(plan)
    summary_bytes = summary_path.read_bytes()
    document = _decode_json_object(summary_bytes, "benchmark summary")
    _validate_summary_document(document, plan)

    results_bytes = results_path.read_bytes()
    rows = _decode_json_lines(results_bytes)
    _validate_rows(rows, plan)
    scores = aggregate_profile_scores(rows)
    if len(scores) != REQUIRED_CANDIDATES:
        raise ValueError("benchmark results must contain all 48 candidate profiles")
    if any(score.scheduled_rows != REQUIRED_ROWS // REQUIRED_CANDIDATES for score in scores):
        raise ValueError("each candidate must contain exactly 682 scheduled rows")
    execution_errors = sum(row["reason"] == "execution_error" for row in rows)
    if execution_errors != document["failed_rows"]:
        raise ValueError("benchmark summary execution-error count mismatches row evidence")

    limitations = document.get("limitations")
    if not isinstance(limitations, list) or any(not isinstance(item, str) for item in limitations):
        raise ValueError("benchmark summary limitations must be a string array")
    contracts = document["contracts"]
    evidence = BenchmarkSummary(
        schema_version=1,
        status=str(document["status"]),
        seed=REQUIRED_SEED,
        corpus_pages=REQUIRED_CORPUS_PAGES,
        candidate_count=REQUIRED_CANDIDATES,
        attack_count=REQUIRED_ATTACKS,
        planned_rows=REQUIRED_ROWS,
        completed_rows=len(rows),
        execution_errors=execution_errors,
        contract_hashes={
            "corpus_sha256": str(contracts["corpus_sha256"]),
            "profiles_sha256": str(contracts["profiles_sha256"]),
            "attack_matrix_sha256": str(contracts["attack_matrix_sha256"]),
        },
        plan_sha256=plan.plan_sha256,
        results_sha256=hashlib.sha256(results_bytes).hexdigest(),
        source_summary_sha256=hashlib.sha256(summary_bytes).hexdigest(),
        profiles=scores,
        limitations=tuple(limitations),
        execution_error_details=_execution_error_details(rows),
    )
    if execution_errors:
        raise NonPromotableBenchmark(evidence)
    return evidence


def promote_profile(
    summary: BenchmarkSummary,
    candidates: str | Path,
    destination: str | Path,
) -> ReleasedProfile:
    """Release the highest-ranked eligible candidate with canonical JSON bytes."""

    output = Path(destination).absolute()
    _validate_baseline_summary_identity(summary)
    ranked = eligible_profiles(summary)
    if not ranked:
        ensure_release_absent(output)
        raise NoEligibleProfile("no eligible fingerprint profile satisfies Gate G1")

    candidate_path = Path(candidates).resolve()
    candidate_document = _decode_json_object(candidate_path.read_bytes(), "candidate contract")
    fixed = candidate_document.get("fixed")
    if not isinstance(fixed, Mapping):
        raise ValueError("candidate contract fixed decisions are missing")
    plan = build_execution_plan(DEFAULT_CORPUS, candidate_path, DEFAULT_MATRIX, REQUIRED_SEED)
    _validate_required_plan(plan)
    selected_score = ranked[0]
    selected = next(
        (candidate for candidate in plan.candidates if candidate.profile_sha256 == selected_score.profile_id),
        None,
    )
    if selected is None:
        raise ValueError("selected measured profile is absent from the candidate contract")
    if _candidate_id(selected) != selected_score.candidate_id:
        raise ValueError("selected measured candidate identity does not match the contract")

    document = {
        "schema_version": 1,
        "profile_version": 1,
        "algorithm": "splitbind-dwt-dct-qim-fingerprint",
        "fixed": _plain(dict(fixed)),
        "candidate": _plain(dict(selected.values)),
        "candidate_provenance": {
            "algorithm_profile_sha256": selected_score.profile_id,
            "candidate_id": selected_score.candidate_id,
        },
        "source_contracts": dict(summary.contract_hashes),
        "benchmark": {
            "baseline_requirements_version": BASELINE_REQUIREMENTS_VERSION,
            "seed": summary.seed,
            "corpus_pages": summary.corpus_pages,
            "candidate_count": summary.candidate_count,
            "attack_count": summary.attack_count,
            "planned_rows": summary.planned_rows,
            "completed_rows": summary.completed_rows,
            "execution_errors": summary.execution_errors,
            "plan_sha256": summary.plan_sha256,
            "results_sha256": summary.results_sha256,
        },
        "gate_measurements": _gate_document(selected_score),
        "selection": {
            "eligible_profiles": len(ranked),
            "selected_rank": 1,
            "ordering": [
                "highest_mean_ssim",
                "highest_worst_required_decode_rate",
                "lowest_attack_and_decode_ms_per_page",
                "algorithm_profile_sha256_ascending",
            ],
        },
        "limitations": list(summary.limitations)
        + [
            "Measurements use the versioned synthetic acceptance corpus and are not a commercial robustness guarantee.",
            "Processing milliseconds are attack-and-decode measurements per scheduled page row, not end-to-end worker latency.",
            "A matched issuance identifies a matching issued copy; it does not prove who leaked, edited, or distributed a document.",
        ],
    }
    content = (_canonical_json(document) + "\n").encode("utf-8")
    if output.is_symlink():
        raise FileExistsError("release destination is a symlink")
    if output.exists():
        if not output.is_file():
            raise IsADirectoryError(f"release destination is not a file: {output}")
        if output.read_bytes() != content:
            raise FileExistsError(
                "release destination already exists with different bytes; use an explicit new version"
            )
    else:
        _atomic_write(output, content)
    return ReleasedProfile(
        profile_id=selected_score.profile_id,
        candidate_id=selected_score.candidate_id,
        destination=output,
        document_sha256=hashlib.sha256(content).hexdigest(),
    )


def ensure_release_absent(destination: str | Path) -> None:
    """Remove only the exact stale release-file destination, never a directory."""

    output = Path(destination).absolute()
    if output.exists() or output.is_symlink():
        if not output.is_file() and not output.is_symlink():
            raise IsADirectoryError(f"release destination is not a file: {output}")
        output.unlink()


def write_evaluation_report(
    summary: BenchmarkSummary,
    destination: str | Path,
    released: ReleasedProfile | None,
) -> None:
    """Write a deterministic factual Markdown report covering every candidate."""

    status = "Released" if released is not None else "No release"
    lines = [
        "# Fingerprint profile v1 evaluation",
        "",
        f"**Outcome:** {status}.",
        "",
        "This report reaggregates the complete row-level benchmark evidence. It does not trust the A4 pre-aggregated detection fields.",
        "",
        "## Evidence identity",
        "",
        f"- Seed: `{summary.seed}`.",
        f"- Baseline requirements version: `{BASELINE_REQUIREMENTS_VERSION}`.",
        f"- Plan: {summary.corpus_pages} corpus pages × {summary.candidate_count} candidates × {summary.attack_count} attacks = {summary.planned_rows:,} unique scheduled rows.",
        f"- Completed rows: {summary.completed_rows:,}; execution errors: {summary.execution_errors}.",
        f"- Run status: `{summary.status}` with {summary.execution_errors} execution errors.",
        f"- Plan SHA-256: `{summary.plan_sha256}`.",
        f"- Results JSONL SHA-256: `{summary.results_sha256}`.",
        f"- Corpus contract SHA-256: `{summary.contract_hashes['corpus_sha256']}`.",
        f"- Candidate contract SHA-256: `{summary.contract_hashes['profiles_sha256']}`.",
        f"- Attack-matrix contract SHA-256: `{summary.contract_hashes['attack_matrix_sha256']}`.",
        "",
        "## Gate definitions and denominators",
        "",
        "A candidate passes only with zero false attributions across all 682 scheduled rows; JPEG quality 70 and resize 0.75 each decode at least 95% of their 12 scheduled positive pages; crop 0.25 decodes at least 90% of its geometry-eligible positive pages; and mean clean-watermarked quality across 12 clean watermarked positive pages is at least 38 dB PSNR and 0.95 SSIM.",
        "",
        "Every positive execution error is a failed detection. Every wrong non-null issuance ID is a false attribution, including negative controls and crop-ineligible rows.",
        "",
        "Quality scope is exactly `original_vs_watermarked_before_attack`; the data range is exactly `255` uint8 unsigned intensity levels; and the denominator is exactly 12 unique positive candidate/page pairs. PSNR is measured in dB; SSIM is dimensionless. Processing time is mean attack-and-decode milliseconds per scheduled page row.",
        "",
        "## Candidate results",
        "",
        "| Profile SHA-256 | Candidate ID | False attributions / 682 rows | Execution errors / 682 rows | JPEG-70 | Resize-0.75 | Crop-0.25 eligible | Mean PSNR (dB) | Mean SSIM | Mean attack+decode (ms/page) | Failed gates |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for score in summary.profiles:
        failed = ", ".join(score.failed_gates) if score.failed_gates else "none"
        lines.append(
            "| "
            f"`{score.profile_id}` | `{score.candidate_id}` | {score.false_attribution} / {score.scheduled_rows} | "
            f"{score.execution_errors} / {score.scheduled_rows} | "
            f"{score.jpeg70_true_attribution} / {score.jpeg70_denominator} ({score.jpeg70_rate:.6f}) | "
            f"{score.resize075_true_attribution} / {score.resize075_denominator} ({score.resize075_rate:.6f}) | "
            f"{score.crop025_true_attribution} / {score.crop025_denominator} ({score.crop025_rate:.6f}) | "
            f"{score.mean_psnr_db:.6f} | {score.mean_ssim:.9f} | "
            f"{score.processing_ms_per_page:.6f} | {failed} |"
        )
    lines.extend(["", "## Selection", ""])
    if released is None:
        lines.append("No candidate satisfied every Gate G1 predicate, so no version-1 release artifact was created.")
    else:
        selected = next(score for score in summary.profiles if score.profile_id == released.profile_id)
        lines.extend(
            [
                f"Released `{released.profile_id}` to `{released.destination.name}`.",
                "",
                "Eligible candidates were ordered by highest mean SSIM, then highest worst required decode rate, then lowest mean attack-and-decode milliseconds per page, then profile SHA-256 ascending as the deterministic final tie-break.",
                "",
                f"Selected gate measurements: `{json.dumps(_gate_document(selected), sort_keys=True, separators=(',', ':'))}`.",
            ]
        )
    if summary.execution_error_details:
        lines.extend(["", "## Execution-error details", ""])
        for detail in summary.execution_error_details:
            lines.append(f"- {detail}")
    lines.extend(["", "## Limitations", ""])
    for limitation in summary.limitations:
        lines.append(f"- {limitation}")
    lines.extend(
        [
            "- Measurements apply to the versioned synthetic acceptance corpus and exact attack matrix only.",
            "- Process RSS is a process-lifetime high-water mark and is not isolated production-worker RSS.",
            "- A matching issuance is evidence of a matching issued copy, not proof of who leaked, edited, or distributed it.",
            "",
        ]
    )
    _atomic_write(Path(destination).absolute(), "\n".join(lines).encode("utf-8"))


def _gate_document(score: ProfileScore) -> dict[str, object]:
    return {
        "false_attribution": {
            "count": score.false_attribution,
            "denominator_scheduled_rows": score.scheduled_rows,
            "threshold": 0,
        },
        "execution_errors": {
            "count": score.execution_errors,
            "threshold": 0,
        },
        "jpeg70": {
            "true_attributions": score.jpeg70_true_attribution,
            "denominator_positive_pages": score.jpeg70_denominator,
            "decode_rate": score.jpeg70_rate,
            "threshold": 0.95,
        },
        "resize075": {
            "true_attributions": score.resize075_true_attribution,
            "denominator_positive_pages": score.resize075_denominator,
            "decode_rate": score.resize075_rate,
            "threshold": 0.95,
        },
        "crop025": {
            "true_attributions": score.crop025_true_attribution,
            "denominator_geometry_eligible_positive_pages": score.crop025_denominator,
            "decode_rate": score.crop025_rate,
            "threshold": 0.90,
        },
        "quality_observations": score.quality_observations,
        "mean_psnr_db": {"value": score.mean_psnr_db, "threshold_db": 38.0},
        "mean_ssim": {"value": score.mean_ssim, "threshold": 0.95},
        "quality": {
            "population_observations": score.quality_observations,
            "required_population": 12,
            "population_denominator": "unique_positive_candidate_page_pairs",
            "scope": "original_vs_watermarked_before_attack",
            "data_range": 255,
            "data_range_units": "uint8_unsigned_intensity_levels",
            "mean_psnr": {
                "value": score.mean_psnr_db,
                "threshold": 38.0,
                "units": "dB",
                "denominator_observations": score.quality_observations,
            },
            "mean_ssim": {
                "value": score.mean_ssim,
                "threshold": 0.95,
                "units": "dimensionless",
                "denominator_observations": score.quality_observations,
            },
        },
        "processing": {
            "observations": score.processing_observations,
            "mean_attack_and_decode_ms_per_page": score.processing_ms_per_page,
        },
        "failed_gates": list(score.failed_gates),
    }


def _execution_error_details(rows: Sequence[Mapping[str, object]]) -> tuple[str, ...]:
    observed: Counter[tuple[str, str]] = Counter()
    for row in rows:
        if row.get("reason") != "execution_error":
            continue
        fixture_id = _required_string(row, "fixture_id")
        limitations = row.get("limitations")
        if not isinstance(limitations, list) or any(not isinstance(item, str) for item in limitations):
            raise ValueError("execution-error limitations must be a string array")
        message = next(
            (item for item in limitations if item.startswith("embedding ")),
            "execution error without a specific diagnostic",
        )
        observed[(fixture_id, message)] += 1
    return tuple(
        f"{fixture_id}: {message} ({count} rows)"
        for (fixture_id, message), count in sorted(observed.items())
    )


def _aggregate_one(profile_id: str, rows: Sequence[Mapping[str, object]]) -> ProfileScore:
    candidate_ids = {_required_string(row, "candidate_id") for row in rows}
    if len(candidate_ids) != 1:
        raise ValueError(f"candidate {profile_id} has inconsistent candidate identity")
    false_attribution = 0
    execution_errors = 0
    elapsed: list[float] = []
    quality: dict[tuple[str, int], tuple[float, float]] = {}
    required: dict[str, list[Mapping[str, object]]] = {
        "jpeg70": [],
        "resize075": [],
        "crop025": [],
    }
    for row in rows:
        is_execution_error = _required_string(row, "reason") == "execution_error"
        if is_execution_error:
            execution_errors += 1
        expected = _optional_string(row, "expected_id")
        decoded = _optional_string(row, "decoded_id")
        if decoded is not None and decoded != expected:
            false_attribution += 1
        milliseconds = _finite_number(row, "elapsed_ms")
        if milliseconds < 0.0:
            raise ValueError("elapsed_ms must be finite and non-negative")
        elapsed.append(milliseconds)
        if expected is not None and not is_execution_error:
            if row.get("quality_scope") != "original_vs_watermarked_before_attack":
                raise ValueError("positive quality observation has invalid scope")
            if _finite_number(row, "quality_data_range") != 255.0:
                raise ValueError("quality observation must use uint8 unsigned dynamic range 255")
            psnr = _finite_number(row, "psnr_db")
            ssim = _finite_number(row, "ssim")
            if not 0.0 <= ssim <= 1.0:
                raise ValueError("SSIM must be finite and within [0, 1]")
            key = (_required_string(row, "fixture_id"), _required_integer(row, "page_index"))
            observation = (psnr, ssim)
            previous = quality.setdefault(key, observation)
            if previous != observation:
                raise ValueError("repeated clean quality observation is inconsistent")
        if expected is not None:
            attack_kind = _required_string(row, "attack_kind")
            parameters = row.get("attack_parameters")
            if not isinstance(parameters, Mapping):
                raise ValueError("attack_parameters must be an object")
            if attack_kind == "jpeg" and parameters.get("quality") == 70:
                required["jpeg70"].append(row)
            if attack_kind == "resize" and parameters.get("scale") == 0.75:
                required["resize075"].append(row)
            if attack_kind == "crop" and parameters.get("fraction") == 0.25:
                required["crop025"].append(row)

    jpeg_true, jpeg_denominator = _decode_counts(required["jpeg70"])
    resize_true, resize_denominator = _decode_counts(required["resize075"])
    eligible_crop = [row for row in required["crop025"] if _required_bool(row, "eligible")]
    crop_true, crop_denominator = _decode_counts(eligible_crop)
    jpeg_rate = _rate(jpeg_true, jpeg_denominator)
    resize_rate = _rate(resize_true, resize_denominator)
    crop_rate = _rate(crop_true, crop_denominator)
    mean_psnr = sum(value[0] for value in quality.values()) / len(quality) if quality else math.nan
    mean_ssim = sum(value[1] for value in quality.values()) / len(quality) if quality else math.nan
    processing = sum(elapsed) / len(elapsed) if elapsed else math.nan
    failed = []
    if execution_errors != 0:
        failed.append("benchmark_execution_errors_zero")
    if false_attribution != 0:
        failed.append("false_attribution_zero")
    if not math.isfinite(jpeg_rate) or jpeg_rate < 0.95:
        failed.append("jpeg70_decode_rate_at_least_0.95")
    if not math.isfinite(resize_rate) or resize_rate < 0.95:
        failed.append("resize075_decode_rate_at_least_0.95")
    if not math.isfinite(crop_rate) or crop_rate < 0.90:
        failed.append("crop025_decode_rate_at_least_0.90")
    if not math.isfinite(mean_psnr) or mean_psnr < 38.0:
        failed.append("mean_psnr_db_at_least_38")
    if not math.isfinite(mean_ssim) or mean_ssim < 0.95:
        failed.append("mean_ssim_at_least_0.95")
    if len(quality) != 12:
        failed.append("complete_quality_population_12")
    return ProfileScore(
        profile_id=profile_id,
        candidate_id=next(iter(candidate_ids)),
        false_attribution=false_attribution,
        execution_errors=execution_errors,
        scheduled_rows=len(rows),
        jpeg70_true_attribution=jpeg_true,
        jpeg70_denominator=jpeg_denominator,
        jpeg70_rate=jpeg_rate,
        resize075_true_attribution=resize_true,
        resize075_denominator=resize_denominator,
        resize075_rate=resize_rate,
        crop025_true_attribution=crop_true,
        crop025_denominator=crop_denominator,
        crop025_rate=crop_rate,
        quality_observations=len(quality),
        mean_psnr_db=mean_psnr,
        mean_ssim=mean_ssim,
        processing_observations=len(elapsed),
        processing_ms_per_page=processing,
        failed_gates=tuple(failed),
    )


def _decode_counts(rows: Sequence[Mapping[str, object]]) -> tuple[int, int]:
    true = sum(
        _required_string(row, "reason") != "execution_error"
        and _optional_string(row, "decoded_id") == _required_string(row, "expected_id")
        for row in rows
    )
    return true, len(rows)


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else math.nan


def _validate_required_plan(plan: ExecutionPlan) -> None:
    actual = (
        plan.seed,
        plan.smoke,
        plan.corpus_pages,
        plan.candidate_count,
        plan.attack_count,
        plan.planned_rows,
    )
    required = (
        REQUIRED_SEED,
        False,
        REQUIRED_CORPUS_PAGES,
        REQUIRED_CANDIDATES,
        REQUIRED_ATTACKS,
        REQUIRED_ROWS,
    )
    if actual != required:
        raise ValueError("candidate, corpus, and matrix contracts do not form the exact A4 full plan")
    hashes = {
        "corpus_sha256": plan.corpus_contract_sha256,
        "profiles_sha256": plan.profile_contract_sha256,
        "attack_matrix_sha256": plan.attack_matrix_sha256,
    }
    if hashes != REQUIRED_CONTRACT_HASHES:
        raise ValueError("runtime contract bytes do not match pinned A5 baseline v1 hashes")
    if plan.plan_sha256 != REQUIRED_PLAN_SHA256:
        raise ValueError("runtime plan does not match pinned A5 baseline v1 plan SHA-256")


def _require_complete_error_free_summary(summary: BenchmarkSummary) -> None:
    if summary.status != "complete":
        if summary.execution_errors:
            raise NonPromotableBenchmark(summary)
        raise ValueError("promotion requires benchmark status exactly complete")
    if summary.execution_errors != 0:
        raise NonPromotableBenchmark(summary)


def _validate_baseline_summary_identity(summary: BenchmarkSummary) -> None:
    _require_complete_error_free_summary(summary)
    actual = (
        summary.schema_version,
        summary.seed,
        summary.corpus_pages,
        summary.candidate_count,
        summary.attack_count,
        summary.planned_rows,
        summary.completed_rows,
    )
    required = (
        1,
        REQUIRED_SEED,
        REQUIRED_CORPUS_PAGES,
        REQUIRED_CANDIDATES,
        REQUIRED_ATTACKS,
        REQUIRED_ROWS,
        REQUIRED_ROWS,
    )
    if actual != required:
        raise ValueError("benchmark summary is not the exact A5 baseline v1 population")
    if dict(summary.contract_hashes) != REQUIRED_CONTRACT_HASHES:
        raise ValueError("benchmark summary does not identify pinned A5 baseline v1 contracts")
    if summary.plan_sha256 != REQUIRED_PLAN_SHA256:
        raise ValueError("benchmark summary does not identify the pinned A5 baseline v1 plan")


def _validate_summary_document(document: Mapping[str, object], plan: ExecutionPlan) -> None:
    if type(document.get("schema_version")) is not int or document["schema_version"] != 1:
        raise ValueError("benchmark summary schema_version must be 1")
    status = document.get("status")
    if status not in {"complete", "complete_with_errors"} or document.get("complete") is not True:
        raise ValueError("promotion requires a complete benchmark run")
    if document.get("smoke") is not False:
        raise ValueError("promotion rejects smoke evidence")
    if document.get("shard_index") != 0 or document.get("shard_count") != 1:
        raise ValueError("promotion requires one complete unsharded run")
    if document.get("seed") != REQUIRED_SEED:
        raise ValueError("benchmark seed does not match 20260827")
    for field in ("planned_rows", "planned_shard_rows", "completed_rows"):
        if document.get(field) != REQUIRED_ROWS:
            raise ValueError("benchmark must contain exactly 32,736 completed rows")
    failed_rows = document.get("failed_rows")
    if isinstance(failed_rows, bool) or not isinstance(failed_rows, int) or failed_rows < 0:
        raise ValueError("benchmark failed_rows must be a non-negative integer")
    if (status == "complete") != (failed_rows == 0):
        raise ValueError("benchmark status and execution error count disagree")
    contracts = document.get("contracts")
    if not isinstance(contracts, Mapping):
        raise ValueError("benchmark summary contract checksums are missing")
    expected = {
        "corpus_sha256": plan.corpus_contract_sha256,
        "profiles_sha256": plan.profile_contract_sha256,
        "attack_matrix_sha256": plan.attack_matrix_sha256,
        "plan_sha256": plan.plan_sha256,
    }
    if dict(contracts) != expected:
        raise ValueError("benchmark contract/checksum or plan identity mismatch")


def _validate_rows(rows: Sequence[Mapping[str, object]], plan: ExecutionPlan) -> None:
    if len(rows) != REQUIRED_ROWS:
        raise ValueError("results.jsonl must contain exactly 32,736 rows")
    observed_ids: set[str] = set()
    candidates = {candidate.profile_sha256: candidate for candidate in plan.candidates}
    sources = {source.fixture_id: source for source in plan.sources}
    attacks = {attack.case_id: attack for attack in plan.attacks}
    canvas_width, canvas_height = _benchmark_dimensions(plan.candidates)
    expected_keys = {
        (source.fixture_id, page_index, candidate.profile_sha256, attack.case_id)
        for source in plan.sources
        for page_index in range(source.pages)
        for candidate in plan.candidates
        for attack in plan.attacks
    }
    observed_keys: set[tuple[str, int, str, str]] = set()
    for ordinal, row in enumerate(rows):
        row_id = _required_string(row, "row_id")
        if row_id in observed_ids:
            raise ValueError(f"duplicate result row_id at row {ordinal}")
        observed_ids.add(row_id)
        profile_id = _required_string(row, "algorithm_profile_sha256")
        fixture_id = _required_string(row, "fixture_id")
        attack_id = _required_string(row, "attack_id")
        page_index = _required_integer(row, "page_index")
        key = (fixture_id, page_index, profile_id, attack_id)
        if key in observed_keys:
            raise ValueError(f"duplicate scheduled result at row {ordinal}")
        observed_keys.add(key)
        if key not in expected_keys:
            raise ValueError(f"unexpected scheduled result at row {ordinal}")
        candidate = candidates[profile_id]
        source = sources[fixture_id]
        attack = attacks[attack_id]
        expected_row_id = hashlib.sha256(
            f"{fixture_id}\0{page_index}\0{profile_id}\0{attack_id}".encode()
        ).hexdigest()
        if row_id != expected_row_id:
            raise ValueError(f"result row identity mismatch at row {ordinal}")
        _validate_row_provenance(row, plan, candidate, source.kind, attack.kind, attack.parameters)
        expected_issuance = _expected_issuance(plan.seed, fixture_id, page_index, profile_id)
        if source.kind == "negative_external":
            expected_issuance = None
        if _optional_string(row, "expected_id") != expected_issuance:
            raise ValueError(f"ground-truth issuance identity mismatch at row {ordinal}")
        _validate_geometry_eligibility(
            row,
            plan,
            candidate,
            source.kind,
            attack,
            (canvas_height, canvas_width),
        )
    if observed_keys != expected_keys:
        raise ValueError("benchmark results contain missing scheduled rows")


def _validate_row_provenance(
    row: Mapping[str, object],
    plan: ExecutionPlan,
    candidate: Candidate,
    fixture_kind: str,
    attack_kind: str,
    attack_parameters: Mapping[str, object],
) -> None:
    if type(row.get("schema_version")) is not int:
        raise ValueError("result row schema_version must be integer 1")
    expected = {
        "schema_version": 1,
        "corpus_contract_sha256": plan.corpus_contract_sha256,
        "profile_contract_sha256": plan.profile_contract_sha256,
        "attack_matrix_sha256": plan.attack_matrix_sha256,
        "benchmark_plan_sha256": plan.plan_sha256,
        "seed": plan.seed,
        "fixture_kind": fixture_kind,
        "attack_kind": attack_kind,
    }
    for field, value in expected.items():
        if row.get(field) != value:
            raise ValueError(f"result row provenance mismatch for {field}")
    if row.get("attack_parameters") != _plain(dict(attack_parameters)):
        raise ValueError("result row attack parameters mismatch")
    if _required_string(row, "candidate_id") != _candidate_id(candidate):
        raise ValueError("result row candidate identity mismatch")
    reason = _required_string(row, "reason")
    if reason == "execution_error":
        return
    if reason not in {"decoded", "not_detected", "partial", "invalid_crc"}:
        raise ValueError("result row has invalid decode reason")


def _validate_geometry_eligibility(
    row: Mapping[str, object],
    plan: ExecutionPlan,
    candidate: Candidate,
    fixture_kind: str,
    attack: AttackCase,
    page_shape: tuple[int, int],
) -> None:
    expected: tuple[bool, int | None, str] = (True, None, "eligible")
    reason = _required_string(row, "reason")
    crop = _crop_operation(attack)
    if (
        fixture_kind != "negative_external"
        and reason != "execution_error"
        and crop is not None
    ):
        fraction = float(crop.parameters["fraction"])
        height, width = page_shape
        side_scale = math.sqrt(1.0 - fraction)
        retained_width = max(1, round(width * side_scale))
        retained_height = max(1, round(height * side_scale))
        x0 = (width - retained_width) // 2
        y0 = (height - retained_height) // 2
        retained = NormalizedRect(
            x=x0 / width,
            y=y0 / height,
            width=retained_width / width,
            height=retained_height / height,
        )
        page_index = _required_integer(row, "page_index")
        _, key, nonce = _case_context(
            plan.seed,
            _required_string(row, "fixture_id"),
            page_index,
            candidate.profile_sha256,
        )
        profile = {
            "schema_version": 1,
            **candidate.values,
            "document_nonce": nonce,
            "page_index": page_index,
        }
        remaining = _remaining_embedded_tiles(page_shape, key, profile, retained)
        eligible = remaining >= 2
        expected = (
            eligible,
            remaining,
            "at_least_two_complete_embedded_tiles_remain"
            if eligible
            else "fewer_than_two_complete_embedded_tiles_remain",
        )
    actual_remaining = row.get("remaining_embedded_tiles")
    if actual_remaining is not None and (
        isinstance(actual_remaining, bool)
        or not isinstance(actual_remaining, int)
        or actual_remaining < 0
    ):
        raise ValueError("remaining_embedded_tiles must be null or a non-negative integer")
    actual = (
        _required_bool(row, "eligible"),
        actual_remaining,
        _required_string(row, "eligibility_reason"),
    )
    if actual != expected:
        raise ValueError("result row eligibility and remaining-tile geometry mismatch")


def _crop_operation(attack: AttackCase) -> AttackCase | None:
    if attack.kind == "crop":
        return attack
    for operation in attack.operations:
        nested = _crop_operation(operation)
        if nested is not None:
            return nested
    return None


def _candidate_id(candidate: Candidate) -> str:
    values = candidate.values
    return (
        b"SBFP\x01"
        + struct.pack(
            ">IdIII",
            1,
            float(values["qim_delta"]),
            int(values["tile_size_px"]),
            int(values["tiles_per_page"]),
            int(values["payload_repetitions"]),
        )
    ).hex()


def _expected_issuance(seed: int, fixture_id: str, page_index: int, profile_id: str) -> str:
    binding = (
        seed.to_bytes(8, "big")
        + fixture_id.encode("utf-8")
        + b"\x00"
        + page_index.to_bytes(4, "big")
        + bytes.fromhex(profile_id)
    )
    issuance = bytearray(hashlib.sha256(_IDENTITY_DOMAIN + binding).digest()[:16])
    issuance[6] = (issuance[6] & 0x0F) | 0x40
    issuance[8] = (issuance[8] & 0x3F) | 0x80
    return str(UUID(bytes=bytes(issuance)))


def _decode_json_object(content: bytes, label: str) -> Mapping[str, object]:
    try:
        value = json.loads(
            content,
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
            object_pairs_hook=_unique_json_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{label} is not strict JSON") from error
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON object key: {key}")
        value[key] = item
    return value


def _decode_json_lines(content: bytes) -> list[Mapping[str, object]]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("results.jsonl must be UTF-8") from error
    rows = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line:
            raise ValueError(f"results.jsonl contains an empty line at {line_number}")
        value = _decode_json_object(line.encode("utf-8"), f"result row {line_number}")
        rows.append(value)
    return rows


def _plain(value: object) -> object:
    return json.loads(json.dumps(value, sort_keys=True, separators=(",", ":"), default=list))


def _required_string(row: Mapping[str, object], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _optional_string(row: Mapping[str, object], field: str) -> str | None:
    value = row.get(field)
    if value is not None and (not isinstance(value, str) or not value):
        raise ValueError(f"{field} must be null or a non-empty string")
    return value


def _required_integer(row: Mapping[str, object], field: str) -> int:
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _required_bool(row: Mapping[str, object], field: str) -> bool:
    value = row.get(field)
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def _finite_number(row: Mapping[str, object], field: str) -> float:
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number")
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{field} must be finite")
    return converted


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
