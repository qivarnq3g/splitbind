"""Fail-closed V2 fingerprint promotion and the current factual no-release path.

The release boundary deliberately pins Task 6's retained input bytes.  That
selection is valid but empty, therefore this revision can only produce the
factual report; it cannot turn a later substituted full-run artifact into a
release.  A future V2 experiment needs a separately approved source/selection
and full-plan pin before this module can load it for promotion.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import tempfile
from typing import Iterable, Mapping, Sequence

from splitbind_attack.attacks import AttackCase, planned_crop_geometry
from splitbind_attack.ground_truth import NormalizedRect
from splitbind_bench.pregate_v2 import load_qualified_candidate_selection
from splitbind_bench.runner import (
    Candidate,
    ExecutionPlan,
    _benchmark_dimensions,
    _case_context,
    _row_identifier,
    _runtime_v2_profile,
    build_execution_plan,
)
from splitbind_ref.tile_layout_v2 import derive_tiles_v2


ROOT = Path(__file__).resolve().parents[4]
DEFAULT_PROFILES = ROOT / "contracts" / "algorithm" / "fingerprint-candidates.v2.json"
DEFAULT_CORPUS = ROOT / "fixtures" / "corpus" / "corpus-manifest.v1.json"
DEFAULT_MATRIX = ROOT / "contracts" / "algorithm" / "attack-matrix.v1.json"
REQUIRED_SEED = 20260827
REQUIRED_CORPUS_PAGES = 22
REQUIRED_ATTACKS = 31
REQUIRED_V2_CANDIDATE_SHA256 = "e7490f80b69ef1a3289afce40ef02989c9a4d89f00b916055cbf1c4c83a97b88"
REQUIRED_CORPUS_SHA256 = "e5837cd446ab9c9959ba3fc4b85d205ec9d80e91efc6f801d139810b088a77ef"
REQUIRED_MATRIX_SHA256 = "fb3c485d45df15b5f16f76e888be0c2d443d2433ba35cdb1df06a85881a6d40e"
REQUIRED_SELECTION_SHA256 = "709d798da2f494709f24f23a81a79ed5fcd944a7a50cb9a7fb5074f9ba5bc7b1"
REQUIRED_SELECTION_IDS: tuple[str, ...] = ()
REQUIRED_PREGATE_PLAN_SHA256 = "09b02268288e8d75d239b24e36830a8afe44467b1b1a3548805eb7efa8510bff"
REQUIRED_PREGATE_RESULTS_SHA256 = "b99a4d9fcf2e8df880d23294e31dc20887ec15bf888a83f8426a4a1afed87177"
REQUIRED_PREGATE_SUMMARY_SHA256 = "989f0051c634bd8c950d81ad73f7725d0ef42c211c232ecbd4d5fad0d36a3b4b"
# Task 6 selected no candidate.  An absent pin is intentional: it prevents a
# nonempty future run from becoming a release merely by reusing this code.
REQUIRED_FULL_PLAN_SHA256: str | None = None


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
class BenchmarkSummaryV2:
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
    candidate_selection_sha256: str
    profiles: tuple[ProfileScore, ...]
    limitations: tuple[str, ...]
    execution_error_details: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReleasedProfile:
    profile_id: str
    candidate_id: str
    destination: Path
    document_sha256: str


@dataclass(frozen=True, slots=True)
class V2PromotionInputs:
    profiles: Path
    corpus: Path
    matrix: Path
    selection: Path
    selection_sha256: str
    selection_ids: tuple[str, ...]
    selection_document: Mapping[str, object]


class NoEligibleProfileV2(RuntimeError):
    """Raised for valid V2 evidence that contains no Gate G1 candidate."""


class NonPromotableBenchmarkV2(ValueError):
    """Raised when factual full-run evidence cannot be promoted."""


def verify_v2_pinned_inputs(
    profiles: str | Path,
    corpus: str | Path,
    matrix: str | Path,
    selection: str | Path,
) -> V2PromotionInputs:
    """Validate the exact Task 6 source contracts and selection evidence.

    This compares bytes to independently copied constants before trusting the
    self-referential hashes inside the selection and pre-gate artifacts.
    """

    profile_path = Path(profiles).resolve()
    corpus_path = Path(corpus).resolve()
    matrix_path = Path(matrix).resolve()
    selection_path = Path(selection).resolve()
    observed = {
        "profiles": _sha256_file(profile_path),
        "corpus": _sha256_file(corpus_path),
        "matrix": _sha256_file(matrix_path),
        "selection": _sha256_file(selection_path),
    }
    expected = {
        "profiles": REQUIRED_V2_CANDIDATE_SHA256,
        "corpus": REQUIRED_CORPUS_SHA256,
        "matrix": REQUIRED_MATRIX_SHA256,
        "selection": REQUIRED_SELECTION_SHA256,
    }
    if observed != expected:
        raise ValueError("runtime V2 contract or selection bytes do not match pinned hashes")

    document = _decode_json_object(selection_path.read_bytes(), "qualified V2 selection")
    expected_keys = {
        "schema_version",
        "source_contract_sha256",
        "pregate_plan_sha256",
        "pregate_results_sha256",
        "pregate_summary_sha256",
        "qualified_candidate_ids",
    }
    if set(document) != expected_keys:
        raise ValueError("qualified V2 selection has unexpected fields")
    if document.get("schema_version") != 2:
        raise ValueError("qualified V2 selection schema_version must be 2")
    if document.get("source_contract_sha256") != REQUIRED_V2_CANDIDATE_SHA256:
        raise ValueError("qualified V2 selection source contract hash is not pinned")
    if document.get("pregate_plan_sha256") != REQUIRED_PREGATE_PLAN_SHA256:
        raise ValueError("qualified V2 selection pre-gate plan hash is not pinned")
    if document.get("pregate_results_sha256") != REQUIRED_PREGATE_RESULTS_SHA256:
        raise ValueError("qualified V2 selection pre-gate results hash is not pinned")
    if document.get("pregate_summary_sha256") != REQUIRED_PREGATE_SUMMARY_SHA256:
        raise ValueError("qualified V2 selection pre-gate summary hash is not pinned")

    selected = load_qualified_candidate_selection(selection_path, profile_path)
    ids = tuple(value.hex() for value in selected)
    if ids != REQUIRED_SELECTION_IDS:
        raise ValueError("qualified V2 selection candidates do not match the pinned Task 6 decision")
    return V2PromotionInputs(
        profiles=profile_path,
        corpus=corpus_path,
        matrix=matrix_path,
        selection=selection_path,
        selection_sha256=observed["selection"],
        selection_ids=ids,
        selection_document=document,
    )


def eligible_v2_profiles(summary: BenchmarkSummaryV2) -> tuple[ProfileScore, ...]:
    """Return Gate G1 candidates in deterministic rank order."""

    _require_complete_error_free_summary(summary)
    eligible = [
        score
        for score in summary.profiles
        if score.false_attribution == 0
        and score.execution_errors == 0
        and score.jpeg70_rate >= 0.95
        and score.resize075_rate >= 0.95
        and score.crop025_rate >= 0.90
        and score.quality_observations == 12
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


def promote_profile_v2(
    summary: BenchmarkSummaryV2, destination: str | Path
) -> ReleasedProfile:
    """Write a canonical release only from already validated full-run evidence.

    Callers that consume files must use :func:`load_v2_benchmark_summary`
    first; this small object-level function is deliberately testable with
    synthetic, hand-checked Gate G1 summaries.
    """

    _require_complete_error_free_summary(summary)
    output = Path(destination).absolute()
    ranked = eligible_v2_profiles(summary)
    if not ranked:
        ensure_v2_release_absent(output)
        raise NoEligibleProfileV2("no V2 candidate satisfies every unchanged Gate G1 predicate")
    selected_score = ranked[0]
    plan = build_execution_plan(DEFAULT_CORPUS, DEFAULT_PROFILES, DEFAULT_MATRIX, REQUIRED_SEED)
    selected = next(
        (candidate for candidate in plan.candidates if candidate.profile_sha256 == selected_score.profile_id),
        None,
    )
    if selected is None or selected.candidate_id != selected_score.candidate_id:
        raise ValueError("selected V2 profile is absent from the frozen candidate contract")
    contract = _decode_json_object(DEFAULT_PROFILES.read_bytes(), "V2 candidate contract")
    document = {
        "schema_version": 2,
        "profile_version": 2,
        "algorithm": "splitbind-fingerprint-v2",
        "fixed": _plain(contract["fixed"]),
        "candidate": _plain(dict(selected.values)),
        "candidate_provenance": {
            "algorithm_profile_sha256": selected_score.profile_id,
            "candidate_id": selected_score.candidate_id,
        },
        "source_contracts": dict(summary.contract_hashes),
        "benchmark": {
            "seed": summary.seed,
            "corpus_pages": summary.corpus_pages,
            "candidate_count": summary.candidate_count,
            "attack_count": summary.attack_count,
            "planned_rows": summary.planned_rows,
            "completed_rows": summary.completed_rows,
            "execution_errors": summary.execution_errors,
            "plan_sha256": summary.plan_sha256,
            "results_sha256": summary.results_sha256,
            "candidate_selection_sha256": summary.candidate_selection_sha256,
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
        "limitations": list(summary.limitations) + [
            "Measurements apply only to the exact versioned synthetic acceptance corpus and attack matrix.",
            "A matching issuance is evidence of a matching issued copy, not proof of who leaked, edited, or distributed it.",
        ],
    }
    content = (_canonical_json(document) + "\n").encode("utf-8")
    if output.is_symlink():
        raise FileExistsError("release destination is a symlink")
    if output.exists():
        if not output.is_file():
            raise IsADirectoryError(f"release destination is not a file: {output}")
        if output.read_bytes() != content:
            raise FileExistsError("release destination already exists with different bytes")
    else:
        _atomic_write(output, content)
    return ReleasedProfile(
        profile_id=selected_score.profile_id,
        candidate_id=selected_score.candidate_id,
        destination=output,
        document_sha256=hashlib.sha256(content).hexdigest(),
    )


def ensure_v2_release_absent(destination: str | Path) -> None:
    """Unlink only the exact release leaf; never follow or recurse through it."""

    output = Path(destination).absolute()
    if output.exists() or output.is_symlink():
        if not output.is_file() and not output.is_symlink():
            raise IsADirectoryError(f"release destination is not a file: {output}")
        output.unlink()


def promote_v2_after_report(
    summary: BenchmarkSummaryV2, output: str | Path, report: str | Path
) -> ReleasedProfile:
    """Stage a release, finalize its factual report, then publish its leaf.

    The report has the final release identity before publication.  The staging
    sibling is always removed on a failure and is never a directory or a path
    supplied by a caller.
    """

    destination = Path(output).absolute()
    if destination.is_symlink():
        raise FileExistsError("release destination is a symlink")
    if destination.exists() and not destination.is_file():
        raise IsADirectoryError(f"release destination is not a file: {destination}")
    stage = destination.with_name(f".{destination.name}.{secrets.token_hex(16)}.stage")
    try:
        staged = promote_profile_v2(summary, stage)
        if destination.exists() and destination.read_bytes() != stage.read_bytes():
            raise FileExistsError("release destination already exists with different bytes")
        released = ReleasedProfile(
            profile_id=staged.profile_id,
            candidate_id=staged.candidate_id,
            destination=destination,
            document_sha256=staged.document_sha256,
        )
        write_v2_evaluation_report(summary, report, released)
        os.replace(stage, destination)
        return released
    finally:
        if stage.exists() or stage.is_symlink():
            ensure_v2_release_absent(stage)


def load_v2_benchmark_summary(
    summary: str | Path,
    profiles: str | Path,
    selection: str | Path,
    *,
    corpus: str | Path = DEFAULT_CORPUS,
    matrix: str | Path = DEFAULT_MATRIX,
) -> BenchmarkSummaryV2:
    """Strictly load a future, separately pinned, complete V2 full run.

    The current pinned selection is empty.  This therefore fails closed before
    reading any alleged full-matrix report; retaining the generic row validator
    here makes the trust boundary ready for a future approved nonempty pin.
    """

    inputs = verify_v2_pinned_inputs(profiles, corpus, matrix, selection)
    if not inputs.selection_ids:
        raise NoEligibleProfileV2("Task 6 qualified selection is empty; V2 full matrix is forbidden")
    if REQUIRED_FULL_PLAN_SHA256 is None:
        raise ValueError("no separately approved V2 qualified full-plan hash is pinned")
    summary_path = Path(summary).resolve()
    summary_bytes = summary_path.read_bytes()
    document = _decode_json_object(summary_bytes, "V2 benchmark summary")
    plan = build_execution_plan(
        inputs.corpus, inputs.profiles, inputs.matrix, REQUIRED_SEED,
        candidate_selection=inputs.selection,
    )
    _validate_full_plan(plan, inputs)
    _validate_summary_document(document, plan)
    results_bytes = summary_path.with_name("results.jsonl").read_bytes()
    rows = _decode_json_lines(results_bytes)
    _validate_rows(rows, plan)
    scores = aggregate_v2_profile_scores(rows, plan)
    execution_errors = sum(_required_string(row, "reason") == "execution_error" for row in rows)
    if execution_errors != document["failed_rows"]:
        raise ValueError("V2 summary execution-error count mismatches row evidence")
    limitations = document.get("limitations")
    if not isinstance(limitations, list) or any(not isinstance(value, str) for value in limitations):
        raise ValueError("V2 benchmark limitations must be strings")
    evidence = BenchmarkSummaryV2(
        schema_version=2,
        status=_required_string(document, "status"),
        seed=REQUIRED_SEED,
        corpus_pages=plan.corpus_pages,
        candidate_count=plan.candidate_count,
        attack_count=plan.attack_count,
        planned_rows=plan.planned_rows,
        completed_rows=len(rows),
        execution_errors=execution_errors,
        contract_hashes={
            "corpus_sha256": plan.corpus_contract_sha256,
            "profiles_sha256": plan.profile_contract_sha256,
            "attack_matrix_sha256": plan.attack_matrix_sha256,
        },
        plan_sha256=plan.plan_sha256,
        results_sha256=hashlib.sha256(results_bytes).hexdigest(),
        source_summary_sha256=hashlib.sha256(summary_bytes).hexdigest(),
        candidate_selection_sha256=inputs.selection_sha256,
        profiles=scores,
        limitations=tuple(limitations),
        execution_error_details=_execution_error_details(rows),
    )
    if execution_errors:
        raise NonPromotableBenchmarkV2("V2 full matrix contains execution errors")
    return evidence


def aggregate_v2_profile_scores(
    rows: Iterable[Mapping[str, object]], plan: ExecutionPlan
) -> tuple[ProfileScore, ...]:
    """Reaggregate V2 Gate G1 values from complete row evidence only."""

    grouped = {candidate.profile_sha256: [] for candidate in plan.candidates}
    for ordinal, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"V2 result row {ordinal} must be an object")
        profile_id = _required_string(row, "algorithm_profile_sha256")
        if profile_id not in grouped:
            raise ValueError("V2 result row has an unknown profile")
        grouped[profile_id].append(row)
    return tuple(_aggregate_one(profile_id, values) for profile_id, values in sorted(grouped.items()))


def write_v2_evaluation_report(
    summary: BenchmarkSummaryV2, destination: str | Path, released: ReleasedProfile | None
) -> None:
    """Atomically write a factual full-run report before any release publish."""

    status = "Released" if released is not None else "No release"
    lines = [
        "# Fingerprint profile v2 evaluation",
        "",
        f"**Outcome:** {status}.",
        "",
        "This report independently reaggregates complete V2 row evidence. It does not trust pre-aggregated detection fields.",
        "",
        "## Evidence identity",
        "",
        f"- Seed: `{summary.seed}`.",
        f"- Plan: {summary.corpus_pages} corpus pages x {summary.candidate_count} selected candidates x {summary.attack_count} attacks = {summary.planned_rows:,} scheduled rows.",
        f"- Completed rows: {summary.completed_rows:,}; execution errors: {summary.execution_errors}.",
        f"- Plan SHA-256: `{summary.plan_sha256}`.",
        f"- Results JSONL SHA-256: `{summary.results_sha256}`.",
        f"- Qualified-selection SHA-256: `{summary.candidate_selection_sha256}`.",
        "",
        "## Candidate results",
        "",
        "| Profile SHA-256 | False attributions | Execution errors | JPEG-70 | Resize-0.75 | Crop-0.25 eligible | Mean PSNR (dB) | Mean SSIM | Failed gates |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for score in summary.profiles:
        failed = ", ".join(score.failed_gates) if score.failed_gates else "none"
        lines.append(
            f"| `{score.profile_id}` | {score.false_attribution} / {score.scheduled_rows} | "
            f"{score.execution_errors} / {score.scheduled_rows} | "
            f"{score.jpeg70_true_attribution} / {score.jpeg70_denominator} ({score.jpeg70_rate:.6f}) | "
            f"{score.resize075_true_attribution} / {score.resize075_denominator} ({score.resize075_rate:.6f}) | "
            f"{score.crop025_true_attribution} / {score.crop025_denominator} ({score.crop025_rate:.6f}) | "
            f"{score.mean_psnr_db:.6f} | {score.mean_ssim:.9f} | {failed} |"
        )
    lines.extend(["", "## Selection", ""])
    if released is None:
        lines.append("No candidate satisfied every unchanged Gate G1 predicate; no V2 release artifact was created.")
    else:
        lines.append(f"Released `{released.profile_id}` to `{released.destination.name}` after this report was written.")
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {limitation}" for limitation in summary.limitations)
    lines.extend([
        "- Measurements apply only to the versioned synthetic acceptance corpus and exact attack matrix.",
        "- A matching issuance is evidence of a matching issued copy, not proof of who leaked, edited, or distributed it.",
        "",
    ])
    _atomic_write(Path(destination).absolute(), "\n".join(lines).encode("utf-8"))


def write_v2_no_release_report(inputs: V2PromotionInputs, destination: str | Path) -> None:
    """Record the current valid-empty selection without fabricating a full run."""

    selection = inputs.selection_document
    lines = [
        "# Fingerprint profile v2 evaluation",
        "",
        "**Outcome:** No release.",
        "",
        "## Qualified-selection decision",
        "",
        "Task 6 produced a valid, hash-bound empty V2 qualified selection. Consequently the qualified full matrix was not run, and no V2 fingerprint profile was created.",
        "",
        f"- V2 candidate contract SHA-256: `{REQUIRED_V2_CANDIDATE_SHA256}`.",
        f"- Corpus contract SHA-256: `{REQUIRED_CORPUS_SHA256}`.",
        f"- Attack-matrix contract SHA-256: `{REQUIRED_MATRIX_SHA256}`.",
        f"- Qualified-selection SHA-256: `{inputs.selection_sha256}`.",
        f"- Pre-gate plan SHA-256: `{selection['pregate_plan_sha256']}`.",
        f"- Pre-gate results SHA-256: `{selection['pregate_results_sha256']}`.",
        f"- Pre-gate summary SHA-256: `{selection['pregate_summary_sha256']}`.",
        f"- Qualified candidates: {len(inputs.selection_ids)} of 16.",
        "",
        "The retained Task 6 evidence completed all 1,408 pre-gate rows with zero execution errors and zero false attributions, but every candidate missed the JPEG-70, resize-0.75, and geometry-eligible crop-0.25 robustness gates. That cost-control filter is not a full Gate G1 release measurement.",
        "",
        "## Consequence",
        "",
        "No full V2 matrix was executed because its required nonempty qualified selection does not exist. `contracts/algorithm/fingerprint-profile.v2.json` remains absent, and Rust A7 remains blocked pending a separately approved algorithm revision and new measurement evidence.",
        "",
        "## Limitations",
        "",
        "- The result applies only to the fixed synthetic corpus, candidate contract, attack matrix, and seed.",
        "- Watermark matching is not proof of who leaked, edited, or distributed a document.",
        "",
    ]
    _atomic_write(Path(destination).absolute(), "\n".join(lines).encode("utf-8"))


def run_v2_promotion_cli(
    *, summary: str | Path | None, profiles: str | Path, selection: str | Path,
    corpus: str | Path, matrix: str | Path, output: str | Path, report: str | Path,
) -> tuple[int, str]:
    """Execute promotion with report-before-release ordering and exact cleanup."""

    output_path = Path(output).absolute()
    try:
        inputs = verify_v2_pinned_inputs(profiles, corpus, matrix, selection)
        if not inputs.selection_ids:
            write_v2_no_release_report(inputs, report)
            ensure_v2_release_absent(output_path)
            return 2, "no_release_empty_qualified_selection"
        if summary is None:
            raise ValueError("--summary is required for a nonempty qualified V2 selection")
        evidence = load_v2_benchmark_summary(
            summary, profiles, selection, corpus=corpus, matrix=matrix
        )
        ranked = eligible_v2_profiles(evidence)
        if not ranked:
            write_v2_evaluation_report(evidence, report, None)
            ensure_v2_release_absent(output_path)
            return 2, "no_release_no_gate_g1_candidate"
        released = promote_v2_after_report(evidence, output_path, report)
        return 0, json.dumps({"status": "released", "profile_id": released.profile_id}, sort_keys=True)
    except Exception:
        # A nonzero path must remove only the named leaf, including a stale
        # symlink; an unrelated target is never traversed or removed.
        try:
            ensure_v2_release_absent(output_path)
        except Exception:
            pass
        raise


def _aggregate_one(profile_id: str, rows: Sequence[Mapping[str, object]]) -> ProfileScore:
    candidate_ids = {_required_string(row, "candidate_id") for row in rows}
    if len(candidate_ids) != 1:
        raise ValueError("V2 profile rows have inconsistent candidate identity")
    false_attribution = 0
    execution_errors = 0
    elapsed: list[float] = []
    quality: dict[tuple[str, int], tuple[float, float]] = {}
    required: dict[str, list[Mapping[str, object]]] = {"jpeg70": [], "resize075": [], "crop025": []}
    for row in rows:
        reason = _required_string(row, "reason")
        if reason == "execution_error":
            execution_errors += 1
        expected = _optional_string(row, "expected_id")
        decoded = _optional_string(row, "decoded_id")
        if decoded is not None and decoded != expected:
            false_attribution += 1
        elapsed.append(_nonnegative_number(row, "elapsed_ms"))
        if expected is not None:
            if row.get("quality_scope") != "original_vs_watermarked_before_attack":
                raise ValueError("positive V2 quality scope is invalid")
            if _finite_number(row, "quality_data_range") != 255.0:
                raise ValueError("positive V2 quality must use uint8 data range 255")
            psnr, ssim = _finite_number(row, "psnr_db"), _finite_number(row, "ssim")
            if not 0.0 <= ssim <= 1.0:
                raise ValueError("V2 SSIM must be within [0, 1]")
            key = (_required_string(row, "fixture_id"), _required_integer(row, "page_index"))
            prior = quality.setdefault(key, (psnr, ssim))
            if prior != (psnr, ssim):
                raise ValueError("repeated V2 clean quality observation is inconsistent")
            parameters = row.get("attack_parameters")
            if not isinstance(parameters, Mapping):
                raise ValueError("V2 attack parameters must be an object")
            if row.get("attack_kind") == "jpeg" and parameters.get("quality") == 70:
                required["jpeg70"].append(row)
            if row.get("attack_kind") == "resize" and parameters.get("scale") == 0.75:
                required["resize075"].append(row)
            if row.get("attack_kind") == "crop" and parameters.get("fraction") == 0.25:
                required["crop025"].append(row)
    jpeg_true, jpeg_denominator = _decode_counts(required["jpeg70"])
    resize_true, resize_denominator = _decode_counts(required["resize075"])
    crop_rows = [row for row in required["crop025"] if _required_bool(row, "eligible")]
    crop_true, crop_denominator = _decode_counts(crop_rows)
    rates = (_rate(jpeg_true, jpeg_denominator), _rate(resize_true, resize_denominator), _rate(crop_true, crop_denominator))
    mean_psnr = sum(item[0] for item in quality.values()) / len(quality) if quality else math.nan
    mean_ssim = sum(item[1] for item in quality.values()) / len(quality) if quality else math.nan
    failed = []
    if execution_errors:
        failed.append("benchmark_execution_errors_zero")
    if false_attribution:
        failed.append("false_attribution_zero")
    for name, value, threshold in zip(("jpeg70", "resize075", "crop025"), rates, (0.95, 0.95, 0.90), strict=True):
        if not math.isfinite(value) or value < threshold:
            failed.append(f"{name}_decode_rate_at_least_{threshold:.2f}")
    if len(quality) != 12:
        failed.append("complete_quality_population_12")
    if not math.isfinite(mean_psnr) or mean_psnr < 38.0:
        failed.append("mean_psnr_db_at_least_38")
    if not math.isfinite(mean_ssim) or mean_ssim < 0.95:
        failed.append("mean_ssim_at_least_0.95")
    return ProfileScore(
        profile_id, next(iter(candidate_ids)), false_attribution, execution_errors, len(rows),
        jpeg_true, jpeg_denominator, rates[0], resize_true, resize_denominator, rates[1],
        crop_true, crop_denominator, rates[2], len(quality), mean_psnr, mean_ssim,
        len(elapsed), sum(elapsed) / len(elapsed) if elapsed else math.nan, tuple(failed),
    )


def _validate_full_plan(plan: ExecutionPlan, inputs: V2PromotionInputs) -> None:
    expected_rows = REQUIRED_CORPUS_PAGES * len(inputs.selection_ids) * REQUIRED_ATTACKS
    actual = (plan.seed, plan.smoke, plan.algorithm_version, plan.corpus_pages, plan.candidate_count, plan.attack_count, plan.planned_rows)
    expected = (REQUIRED_SEED, False, 2, REQUIRED_CORPUS_PAGES, len(inputs.selection_ids), REQUIRED_ATTACKS, expected_rows)
    if actual != expected or plan.candidate_selection_sha256 != inputs.selection_sha256:
        raise ValueError("V2 full plan is not the exact qualified population")
    if plan.plan_sha256 != REQUIRED_FULL_PLAN_SHA256:
        raise ValueError("V2 full plan hash is not independently pinned")


def _validate_summary_document(document: Mapping[str, object], plan: ExecutionPlan) -> None:
    if document.get("schema_version") != 1 or document.get("algorithm_version") != 2:
        raise ValueError("V2 full summary has the wrong schema or algorithm version")
    if document.get("status") not in {"complete", "complete_with_errors"} or document.get("complete") is not True:
        raise ValueError("V2 promotion requires a complete unsharded benchmark")
    if document.get("smoke") is not False or document.get("shard_index") != 0 or document.get("shard_count") != 1:
        raise ValueError("V2 promotion rejects smoke and sharded evidence")
    for field in ("planned_rows", "planned_shard_rows", "completed_rows"):
        if document.get(field) != plan.planned_rows:
            raise ValueError("V2 full summary row count mismatches its plan")
    failed = document.get("failed_rows")
    if isinstance(failed, bool) or not isinstance(failed, int) or failed < 0:
        raise ValueError("V2 full summary failed_rows is invalid")
    if (document["status"] == "complete") != (failed == 0):
        raise ValueError("V2 full summary status and execution errors disagree")
    contracts = document.get("contracts")
    expected_contracts = {
        "corpus_sha256": plan.corpus_contract_sha256,
        "profiles_sha256": plan.profile_contract_sha256,
        "attack_matrix_sha256": plan.attack_matrix_sha256,
        "plan_sha256": plan.plan_sha256,
        "candidate_selection_sha256": plan.candidate_selection_sha256,
    }
    if not isinstance(contracts, Mapping) or dict(contracts) != expected_contracts:
        raise ValueError("V2 full summary contract/selection provenance mismatches")


def _validate_rows(rows: Sequence[Mapping[str, object]], plan: ExecutionPlan) -> None:
    if len(rows) != plan.planned_rows:
        raise ValueError("V2 results contain missing or surplus rows")
    candidates = {candidate.profile_sha256: candidate for candidate in plan.candidates}
    sources = {source.fixture_id: source for source in plan.sources}
    attacks = {attack.case_id: attack for attack in plan.attacks}
    expected = {
        (source.fixture_id, page_index, candidate.profile_sha256, attack.case_id)
        for source in plan.sources for page_index in range(source.pages)
        for candidate in plan.candidates for attack in plan.attacks
    }
    seen_rows: set[str] = set()
    seen_keys: set[tuple[str, int, str, str]] = set()
    canvas_width, canvas_height = _benchmark_dimensions(plan.candidates)
    for ordinal, row in enumerate(rows):
        row_id = _required_string(row, "row_id")
        if row_id in seen_rows:
            raise ValueError(f"duplicate V2 result row_id at row {ordinal}")
        seen_rows.add(row_id)
        key = (_required_string(row, "fixture_id"), _required_integer(row, "page_index"), _required_string(row, "algorithm_profile_sha256"), _required_string(row, "attack_id"))
        if key in seen_keys:
            raise ValueError(f"duplicate V2 scheduled row at row {ordinal}")
        seen_keys.add(key)
        if key not in expected:
            raise ValueError(f"unexpected V2 scheduled row at row {ordinal}")
        fixture_id, page_index, profile_id, attack_id = key
        candidate, source, attack = candidates[profile_id], sources[fixture_id], attacks[attack_id]
        if row_id != _row_identifier(fixture_id, page_index, profile_id, attack_id):
            raise ValueError("V2 row identity mismatch")
        _validate_row_provenance(row, plan, candidate, source.kind, attack)
        expected_issuance = None if source.kind == "negative_external" else str(_case_context(plan.seed, fixture_id, page_index, profile_id)[0])
        if _optional_string(row, "expected_id") != expected_issuance:
            raise ValueError("V2 row ground-truth issuance mismatches")
        _validate_crop_eligibility(row, candidate, attack, (canvas_height, canvas_width), plan.seed)
    if seen_keys != expected:
        raise ValueError("V2 results contain missing scheduled rows")


def _validate_row_provenance(row: Mapping[str, object], plan: ExecutionPlan, candidate: Candidate, source_kind: str, attack: AttackCase) -> None:
    expected = {
        "schema_version": 1, "algorithm_version": 2, "corpus_contract_sha256": plan.corpus_contract_sha256,
        "profile_contract_sha256": plan.profile_contract_sha256, "attack_matrix_sha256": plan.attack_matrix_sha256,
        "benchmark_plan_sha256": plan.plan_sha256, "seed": plan.seed, "fixture_kind": source_kind,
        "attack_kind": attack.kind, "candidate_id": candidate.candidate_id,
    }
    for field, value in expected.items():
        if row.get(field) != value:
            raise ValueError(f"V2 row provenance mismatch for {field}")
    if row.get("attack_parameters") != _plain(dict(attack.parameters)):
        raise ValueError("V2 row attack parameters mismatch")
    reason = _required_string(row, "reason")
    if reason not in {"decoded", "not_detected", "partial", "execution_error"}:
        raise ValueError("V2 row decode reason is invalid")
    status = _required_string(row, "algorithm_status")
    if reason == "execution_error" and status != "execution_error":
        raise ValueError("V2 execution error has an invalid status")


def _validate_crop_eligibility(row: Mapping[str, object], candidate: Candidate, attack: AttackCase, page_shape: tuple[int, int], seed: int) -> None:
    crop = _crop_operation(attack)
    expected: tuple[bool, int | None, str] = (True, None, "eligible")
    if crop is not None and _optional_string(row, "expected_id") is not None and _required_string(row, "reason") != "execution_error":
        geometry = planned_crop_geometry(crop, page_shape)
        if geometry is None:
            raise ValueError("V2 crop geometry is unavailable")
        retained, _ = geometry
        _, key, _ = _case_context(seed, _required_string(row, "fixture_id"), _required_integer(row, "page_index"), candidate.profile_sha256)
        profile = _runtime_v2_profile(candidate)
        remaining = _remaining_v2_tiles(page_shape, key, _required_integer(row, "page_index"), profile, retained)
        eligible = remaining >= 2
        expected = (eligible, remaining, "at_least_two_complete_embedded_tiles_remain" if eligible else "fewer_than_two_complete_embedded_tiles_remain")
    actual_remaining = row.get("remaining_embedded_tiles")
    if actual_remaining is not None and (isinstance(actual_remaining, bool) or not isinstance(actual_remaining, int) or actual_remaining < 0):
        raise ValueError("V2 remaining tile count is invalid")
    actual = (_required_bool(row, "eligible"), actual_remaining, _required_string(row, "eligibility_reason"))
    if actual != expected:
        raise ValueError("V2 crop eligibility was not independently reconstructed")


def _remaining_v2_tiles(page_shape: tuple[int, int], key: bytes, page_index: int, profile, retained: NormalizedRect) -> int:
    height, width = page_shape
    tiles = derive_tiles_v2(page_shape, key, page_index, profile)[: profile.payload_repetitions]
    left, top = retained.x * width, retained.y * height
    right, bottom = retained.right * width, retained.bottom * height
    return sum(tile.x >= left and tile.y >= top and tile.x + tile.width <= right and tile.y + tile.height <= bottom for tile in tiles)


def _crop_operation(attack: AttackCase) -> AttackCase | None:
    if attack.kind == "crop":
        return attack
    for nested in attack.operations:
        selected = _crop_operation(nested)
        if selected is not None:
            return selected
    return None


def _gate_document(score: ProfileScore) -> dict[str, object]:
    return {
        "false_attribution": {"count": score.false_attribution, "threshold": 0},
        "execution_errors": {"count": score.execution_errors, "threshold": 0},
        "jpeg70": {"decode_rate": score.jpeg70_rate, "threshold": 0.95, "denominator": score.jpeg70_denominator},
        "resize075": {"decode_rate": score.resize075_rate, "threshold": 0.95, "denominator": score.resize075_denominator},
        "crop025": {"decode_rate": score.crop025_rate, "threshold": 0.90, "denominator_geometry_eligible": score.crop025_denominator},
        "quality": {"observations": score.quality_observations, "required_observations": 12, "mean_psnr_db": score.mean_psnr_db, "mean_ssim": score.mean_ssim},
        "failed_gates": list(score.failed_gates),
    }


def _require_complete_error_free_summary(summary: BenchmarkSummaryV2) -> None:
    if summary.status != "complete":
        raise NonPromotableBenchmarkV2("V2 promotion requires status exactly complete")
    if summary.execution_errors != 0:
        raise NonPromotableBenchmarkV2("V2 promotion requires zero execution errors")


def _decode_counts(rows: Sequence[Mapping[str, object]]) -> tuple[int, int]:
    return sum(_required_string(row, "reason") != "execution_error" and _optional_string(row, "decoded_id") == _required_string(row, "expected_id") for row in rows), len(rows)


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else math.nan


def _execution_error_details(rows: Sequence[Mapping[str, object]]) -> tuple[str, ...]:
    details: Counter[tuple[str, str]] = Counter()
    for row in rows:
        if row.get("reason") != "execution_error":
            continue
        limitations = row.get("limitations")
        message = next((item for item in limitations if isinstance(item, str) and item.startswith(("embedding ", "ValueError", "RuntimeError"))), "execution error without diagnostic") if isinstance(limitations, list) else "execution error without diagnostic"
        details[(_required_string(row, "fixture_id"), message)] += 1
    return tuple(f"{fixture_id}: {message} ({count} rows)" for (fixture_id, message), count in sorted(details.items()))


def _decode_json_object(content: bytes, label: str) -> Mapping[str, object]:
    try:
        value = json.loads(content, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)), object_pairs_hook=_unique_json_object)
    except ValueError as error:
        if str(error).startswith("duplicate JSON object key:"):
            raise
        raise ValueError(f"{label} is not strict JSON") from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not strict JSON") from error
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return value


def _decode_json_lines(content: bytes) -> list[Mapping[str, object]]:
    try:
        lines = content.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError("V2 results.jsonl must be UTF-8") from error
    if any(not line for line in lines):
        raise ValueError("V2 results.jsonl contains an empty line")
    return [_decode_json_object(line.encode("utf-8"), f"V2 result row {index}") for index, line in enumerate(lines, start=1)]


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            raise ValueError(f"duplicate JSON object key: {key}")
        document[key] = value
    return document


def _sha256_file(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"required V2 input is not a file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{field} must be finite")
    return float(value)


def _nonnegative_number(row: Mapping[str, object], field: str) -> float:
    value = _finite_number(row, field)
    if value < 0.0:
        raise ValueError(f"{field} must be non-negative")
    return value


def _plain(value: object) -> object:
    return json.loads(json.dumps(value, sort_keys=True, separators=(",", ":"), default=list))


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
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
