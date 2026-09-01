"""Deterministic, fail-closed fingerprint V2 pre-gate and selection evidence."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Literal, Mapping, Sequence

from splitbind_attack.attacks import AttackCase
from splitbind_attack.ground_truth import NormalizedRect
from splitbind_ref.contracts import fingerprint_candidates_v2, fingerprint_candidates_v2_bytes
from splitbind_ref.fingerprint_v2_profile import candidate_identifier_v2, load_v2_profiles

from .runner import (
    Candidate,
    ExecutionPlan,
    _atomic_write_text,
    _benchmark_dimensions,
    _canonical_json,
    _case_context,
    _plan_digest,
    _remaining_embedded_tiles_v2,
    _row_identifier,
    _run_execution_plan,
    build_execution_plan,
)


ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CORPUS = ROOT / "fixtures" / "corpus" / "corpus-manifest.v1.json"
DEFAULT_MATRIX = ROOT / "contracts" / "algorithm" / "attack-matrix.v1.json"
REQUIRED_SEED = 20260827
REQUIRED_POSITIVE_PAGES = 12
REQUIRED_NEGATIVE_PAGES = 10
REQUIRED_CANDIDATES = 16
REQUIRED_ATTACKS = 4
REQUIRED_ROWS = 1408
_REQUIRED_ATTACK_IDS = ("identity", "jpeg-q70", "resize-s0p75", "crop-f0p25")


@dataclass(frozen=True, slots=True)
class PreGateCandidateScoreV2:
    profile_id: str
    candidate_id: str
    scheduled_rows: int
    execution_errors: int
    false_attribution: int
    jpeg70_true_attribution: int
    jpeg70_denominator: int
    jpeg70_rate: float | None
    resize075_true_attribution: int
    resize075_denominator: int
    resize075_rate: float | None
    crop025_true_attribution: int
    crop025_denominator: int
    crop025_rate: float | None
    quality_observations: int
    mean_psnr_db: float | None
    mean_ssim: float | None
    gradient_completed_attacks: int
    failed_gates: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PreGateSummaryV2:
    status: Literal["complete", "complete_with_errors", "incomplete"]
    planned_rows: int
    completed_rows: int
    execution_errors: int
    contract_hashes: Mapping[str, str]
    plan_sha256: str
    results_sha256: str
    qualified_candidate_ids: tuple[str, ...]
    candidates: tuple[PreGateCandidateScoreV2, ...]
    limitations: tuple[str, ...]


def build_v2_pregate_plan(
    corpus: str | Path,
    profiles: str | Path,
    matrix: str | Path,
    seed: int,
) -> ExecutionPlan:
    """Build the exact 22 x 16 x 4 pre-gate without executing image work."""

    full = build_execution_plan(corpus, profiles, matrix, seed)
    if full.algorithm_version != 2:
        raise ValueError("V2 pre-gate requires a schema_version 2 candidate contract")
    by_id = {attack.case_id: attack for attack in full.attacks}
    try:
        selected = (
            AttackCase("identity", "identity", {}),
            by_id["jpeg-q70"],
            by_id["resize-s0p75"],
            by_id["crop-f0p25"],
        )
    except KeyError as error:
        raise ValueError("attack matrix is missing an exact V2 pre-gate attack") from error
    expected_attack_shapes = (
        ("identity", "identity", {}),
        ("jpeg-q70", "jpeg", {"quality": 70}),
        ("resize-s0p75", "resize", {"scale": 0.75}),
        ("crop-f0p25", "crop", {"fraction": 0.25}),
    )
    actual_attack_shapes = tuple(
        (attack.case_id, attack.kind, dict(attack.parameters)) for attack in selected
    )
    if actual_attack_shapes != expected_attack_shapes:
        raise ValueError("attack matrix does not contain the unchanged pre-gate attacks")
    if (
        full.positive_pages,
        full.negative_pages,
        full.candidate_count,
    ) != (REQUIRED_POSITIVE_PAGES, REQUIRED_NEGATIVE_PAGES, REQUIRED_CANDIDATES):
        raise ValueError("corpus and V2 contract do not form the exact pre-gate population")
    plan_sha256 = _plan_digest(full.sources, full.candidates, selected)
    return replace(
        full,
        attacks=selected,
        attack_count=REQUIRED_ATTACKS,
        planned_rows=REQUIRED_ROWS,
        plan_sha256=plan_sha256,
        run_kind="v2_pregate",
    )


def run_v2_pregate(
    corpus: str | Path,
    profiles: str | Path,
    matrix: str | Path,
    seed: int,
    output_dir: str | Path,
    *,
    max_rows: int | None = None,
) -> PreGateSummaryV2:
    """Run/resume the exact pre-gate and publish hash-bound selection last."""

    plan = build_v2_pregate_plan(corpus, profiles, matrix, seed)
    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    # Invalidate any stale qualified selection before touching checkpointed
    # evidence.  A crash can therefore leave only an empty, hash-invalid file,
    # never a previously qualified selection attached to a new/incomplete run.
    _atomic_write_text(
        destination / "qualified-candidate-ids.json",
        json.dumps(
            {
                "schema_version": 2,
                "source_contract_sha256": plan.profile_contract_sha256,
                "pregate_plan_sha256": plan.plan_sha256,
                "pregate_results_sha256": "0" * 64,
                "pregate_summary_sha256": "0" * 64,
                "qualified_candidate_ids": [],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    _run_execution_plan(plan, destination, max_rows=max_rows)
    results_path = destination / "results.jsonl"
    results_bytes = results_path.read_bytes()
    rows = _decode_json_lines(results_bytes)
    _validate_rows(rows, plan, require_complete=False)
    scores = _aggregate_scores(rows, plan)
    execution_errors = sum(row.get("reason") == "execution_error" for row in rows)
    complete = len(rows) == REQUIRED_ROWS
    status: Literal["complete", "complete_with_errors", "incomplete"] = (
        "complete_with_errors"
        if complete and execution_errors
        else "complete"
        if complete
        else "incomplete"
    )
    preliminary = PreGateSummaryV2(
        status=status,
        planned_rows=REQUIRED_ROWS,
        completed_rows=len(rows),
        execution_errors=execution_errors,
        contract_hashes=_contract_hashes(plan),
        plan_sha256=plan.plan_sha256,
        results_sha256=hashlib.sha256(results_bytes).hexdigest(),
        qualified_candidate_ids=(),
        candidates=scores,
        limitations=(
            "The pre-gate is a deterministic cost-control filter, not release evidence.",
            "Only identity, JPEG 70, resize 0.75, and center crop 0.25 are measured.",
            "Missing synchronization or payload evidence is a measured non-decision; only runtime failures are execution errors.",
        ),
    )
    qualified = _qualified_ids(preliminary)
    summary = replace(preliminary, qualified_candidate_ids=qualified)
    summary_document = _summary_document(summary)
    summary_text = json.dumps(summary_document, indent=2, sort_keys=True, allow_nan=False) + "\n"
    _atomic_write_text(destination / "summary.json", summary_text)
    summary_sha256 = hashlib.sha256(summary_text.encode("utf-8")).hexdigest()
    selection_document = {
        "schema_version": 2,
        "source_contract_sha256": summary.contract_hashes["profiles_sha256"],
        "pregate_plan_sha256": summary.plan_sha256,
        "pregate_results_sha256": summary.results_sha256,
        "pregate_summary_sha256": summary_sha256,
        "qualified_candidate_ids": list(summary.qualified_candidate_ids),
    }
    _atomic_write_text(
        destination / "qualified-candidate-ids.json",
        json.dumps(selection_document, indent=2, sort_keys=True) + "\n",
    )
    return summary


def select_qualified_candidates(
    summary: PreGateSummaryV2, contract: Mapping[str, object]
) -> tuple[bytes, ...]:
    """Validate a summary and return exact qualified identifiers in byte order."""

    if not isinstance(summary, PreGateSummaryV2):
        raise TypeError("summary must be a PreGateSummaryV2")
    if not isinstance(contract, Mapping) or dict(contract) != fingerprint_candidates_v2():
        raise ValueError("V2 selection requires the exact frozen source contract")
    canonical_contract_hash = hashlib.sha256(fingerprint_candidates_v2_bytes()).hexdigest()
    if summary.contract_hashes.get("profiles_sha256") != canonical_contract_hash:
        raise ValueError("pre-gate source contract hash mismatch")
    if summary.planned_rows != REQUIRED_ROWS:
        raise ValueError("pre-gate summary planned row count mismatch")
    if (
        summary.status != "complete"
        or summary.completed_rows != REQUIRED_ROWS
        or summary.execution_errors != 0
    ):
        return ()
    expected = _qualified_ids(summary)
    if tuple(summary.qualified_candidate_ids) != expected:
        raise ValueError("pre-gate qualified candidate list disagrees with measured gates")
    available = {candidate_identifier_v2(profile) for profile in load_v2_profiles()}
    selected = tuple(bytes.fromhex(candidate_id) for candidate_id in expected)
    if any(candidate_id not in available for candidate_id in selected):
        raise ValueError("pre-gate qualified list contains an unknown candidate")
    return selected


def load_v2_pregate_summary(
    summary: str | Path,
    profiles: str | Path,
    *,
    corpus: str | Path = DEFAULT_CORPUS,
    matrix: str | Path = DEFAULT_MATRIX,
) -> PreGateSummaryV2:
    """Independently validate summary/results bytes and reconstruct every gate."""

    summary_path = Path(summary).resolve()
    summary_document = _decode_json_object(summary_path.read_bytes(), "pre-gate summary")
    results_path = summary_path.with_name("results.jsonl")
    results_bytes = results_path.read_bytes()
    rows = _decode_json_lines(results_bytes)
    plan = build_v2_pregate_plan(corpus, profiles, matrix, REQUIRED_SEED)
    _validate_rows(rows, plan, require_complete=True)
    scores = _aggregate_scores(rows, plan)
    evidence = PreGateSummaryV2(
        status=_required_status(summary_document),
        planned_rows=_required_integer(summary_document, "planned_rows"),
        completed_rows=_required_integer(summary_document, "completed_rows"),
        execution_errors=_required_integer(summary_document, "execution_errors"),
        contract_hashes=_required_contract_hashes(summary_document),
        plan_sha256=_required_sha256(summary_document, "plan_sha256"),
        results_sha256=_required_sha256(summary_document, "results_sha256"),
        qualified_candidate_ids=_required_string_tuple(
            summary_document, "qualified_candidate_ids"
        ),
        candidates=scores,
        limitations=_required_string_tuple(summary_document, "limitations"),
    )
    expected_document = _summary_document(evidence)
    if summary_document != expected_document:
        raise ValueError("pre-gate summary fields or candidate aggregates were tampered")
    if evidence.contract_hashes != _contract_hashes(plan):
        raise ValueError("pre-gate summary contract hashes mismatch")
    if evidence.plan_sha256 != plan.plan_sha256:
        raise ValueError("pre-gate summary plan hash mismatch")
    if evidence.results_sha256 != hashlib.sha256(results_bytes).hexdigest():
        raise ValueError("pre-gate results hash mismatch")
    select_qualified_candidates(evidence, fingerprint_candidates_v2())
    return evidence


def load_qualified_candidate_selection(
    selection: str | Path, profiles: str | Path
) -> tuple[bytes, ...]:
    """Validate an atomic selection against its sibling pre-gate evidence."""

    selection_path = Path(selection).resolve()
    document = _decode_json_object(selection_path.read_bytes(), "candidate selection")
    expected_keys = {
        "schema_version",
        "source_contract_sha256",
        "pregate_plan_sha256",
        "pregate_results_sha256",
        "pregate_summary_sha256",
        "qualified_candidate_ids",
    }
    if set(document) != expected_keys:
        raise ValueError("candidate selection must contain the exact V2 evidence fields")
    if document.get("schema_version") != 2:
        raise ValueError("candidate selection schema_version must be integer 2")
    profile_path = Path(profiles).resolve()
    profile_hash = hashlib.sha256(profile_path.read_bytes()).hexdigest()
    if document.get("source_contract_sha256") != profile_hash:
        raise ValueError("candidate selection source contract hash mismatch")
    ids = _required_string_tuple(document, "qualified_candidate_ids")
    if tuple(sorted(set(ids))) != ids:
        raise ValueError("qualified candidate identifiers must be sorted and unique")
    available = {candidate_identifier_v2(profile).hex() for profile in load_v2_profiles()}
    if any(candidate_id not in available for candidate_id in ids):
        raise ValueError("candidate selection contains an unknown candidate identifier")
    summary_path = selection_path.with_name("summary.json")
    results_path = selection_path.with_name("results.jsonl")
    summary_bytes = summary_path.read_bytes()
    results_bytes = results_path.read_bytes()
    if document.get("pregate_summary_sha256") != hashlib.sha256(summary_bytes).hexdigest():
        raise ValueError("candidate selection summary hash mismatch")
    if document.get("pregate_results_sha256") != hashlib.sha256(results_bytes).hexdigest():
        raise ValueError("candidate selection results hash mismatch")
    evidence = load_v2_pregate_summary(summary_path, profile_path)
    if document.get("pregate_plan_sha256") != evidence.plan_sha256:
        raise ValueError("candidate selection plan hash mismatch")
    selected = select_qualified_candidates(evidence, fingerprint_candidates_v2())
    if tuple(value.hex() for value in selected) != ids:
        raise ValueError("candidate selection identifiers were tampered")
    return selected


def _aggregate_scores(
    rows: Sequence[Mapping[str, object]], plan: ExecutionPlan
) -> tuple[PreGateCandidateScoreV2, ...]:
    grouped: dict[str, list[Mapping[str, object]]] = {
        candidate.profile_sha256: [] for candidate in plan.candidates
    }
    for row in rows:
        profile_id = _required_string(row, "algorithm_profile_sha256")
        if profile_id not in grouped:
            raise ValueError("result row contains an unknown V2 profile")
        grouped[profile_id].append(row)
    candidates = {candidate.profile_sha256: candidate for candidate in plan.candidates}
    return tuple(
        _aggregate_one(candidates[profile_id], grouped[profile_id])
        for profile_id in sorted(grouped)
    )


def _aggregate_one(
    candidate: Candidate, rows: Sequence[Mapping[str, object]]
) -> PreGateCandidateScoreV2:
    candidate_ids = {_required_string(row, "candidate_id") for row in rows}
    if rows and candidate_ids != {candidate.candidate_id}:
        raise ValueError("candidate rows contain inconsistent candidate identity")
    execution_errors = sum(row.get("reason") == "execution_error" for row in rows)
    false_attribution = sum(
        row.get("decoded_id") is not None and row.get("decoded_id") != row.get("expected_id")
        for row in rows
    )
    required: dict[str, list[Mapping[str, object]]] = {
        "jpeg-q70": [],
        "resize-s0p75": [],
        "crop-f0p25": [],
    }
    quality: dict[tuple[str, int], tuple[float, float]] = {}
    gradient_completed = 0
    for row in rows:
        expected = row.get("expected_id")
        is_error = row.get("reason") == "execution_error"
        if row.get("fixture_id") == "image-clean-gradient" and not is_error:
            gradient_completed += 1
        if expected is not None:
            attack_id = _required_string(row, "attack_id")
            if attack_id in required:
                required[attack_id].append(row)
            if not is_error:
                if row.get("quality_scope") != "original_vs_watermarked_before_attack":
                    raise ValueError("positive quality scope mismatch")
                if _required_number(row, "quality_data_range") != 255.0:
                    raise ValueError("quality data range must be uint8 255")
                observation = (
                    _required_number(row, "psnr_db"),
                    _required_number(row, "ssim"),
                )
                key = (
                    _required_string(row, "fixture_id"),
                    _required_integer(row, "page_index"),
                )
                previous = quality.setdefault(key, observation)
                if previous != observation:
                    raise ValueError("repeated quality observations disagree")
    jpeg_true, jpeg_denominator = _decode_counts(required["jpeg-q70"])
    resize_true, resize_denominator = _decode_counts(required["resize-s0p75"])
    eligible_crop = [row for row in required["crop-f0p25"] if row.get("eligible") is True]
    crop_true, crop_denominator = _decode_counts(eligible_crop)
    jpeg_rate = _rate(jpeg_true, jpeg_denominator)
    resize_rate = _rate(resize_true, resize_denominator)
    crop_rate = _rate(crop_true, crop_denominator)
    mean_psnr = sum(value[0] for value in quality.values()) / len(quality) if quality else None
    mean_ssim = sum(value[1] for value in quality.values()) / len(quality) if quality else None
    failed: list[str] = []
    if execution_errors:
        failed.append("execution_errors_zero")
    if false_attribution:
        failed.append("false_attribution_zero")
    if jpeg_rate is None or jpeg_rate < 0.95:
        failed.append("jpeg70_decode_rate_at_least_0.95")
    if resize_rate is None or resize_rate < 0.95:
        failed.append("resize075_decode_rate_at_least_0.95")
    if crop_rate is None or crop_rate < 0.90:
        failed.append("crop025_decode_rate_at_least_0.90")
    if mean_psnr is None or mean_psnr < 38.0:
        failed.append("mean_psnr_db_at_least_38")
    if mean_ssim is None or mean_ssim < 0.95:
        failed.append("mean_ssim_at_least_0.95")
    if len(quality) != REQUIRED_POSITIVE_PAGES:
        failed.append("complete_quality_population_12")
    if gradient_completed != REQUIRED_ATTACKS:
        failed.append("gradient_completed_all_four_attacks")
    return PreGateCandidateScoreV2(
        profile_id=candidate.profile_sha256,
        candidate_id=candidate.candidate_id or "",
        scheduled_rows=len(rows),
        execution_errors=execution_errors,
        false_attribution=false_attribution,
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
        gradient_completed_attacks=gradient_completed,
        failed_gates=tuple(failed),
    )


def _validate_rows(
    rows: Sequence[Mapping[str, object]],
    plan: ExecutionPlan,
    *,
    require_complete: bool,
) -> None:
    if len(rows) > REQUIRED_ROWS or (require_complete and len(rows) != REQUIRED_ROWS):
        raise ValueError("pre-gate results contain a missing or excess row population")
    sources = {source.fixture_id: source for source in plan.sources}
    candidates = {candidate.profile_sha256: candidate for candidate in plan.candidates}
    attacks = {attack.case_id: attack for attack in plan.attacks}
    expected_keys = [
        (source.fixture_id, page_index, candidate.profile_sha256, attack.case_id)
        for source in plan.sources
        for page_index in range(source.pages)
        for candidate in plan.candidates
        for attack in plan.attacks
    ]
    expected_set = set(expected_keys)
    observed: set[tuple[str, int, str, str]] = set()
    observed_row_ids: set[str] = set()
    canvas_width, canvas_height = _benchmark_dimensions(plan.candidates)
    for ordinal, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"pre-gate row {ordinal} must be an object")
        fixture_id = _required_string(row, "fixture_id")
        page_index = _required_integer(row, "page_index")
        profile_id = _required_string(row, "algorithm_profile_sha256")
        attack_id = _required_string(row, "attack_id")
        key = (fixture_id, page_index, profile_id, attack_id)
        if key in observed:
            raise ValueError("pre-gate results contain a duplicate scheduled row")
        if key not in expected_set:
            raise ValueError("pre-gate results contain an unexpected scheduled row")
        observed.add(key)
        row_id = _required_string(row, "row_id")
        if row_id in observed_row_ids or row_id != _row_identifier(*key):
            raise ValueError("pre-gate row identity is duplicate or invalid")
        observed_row_ids.add(row_id)
        source = sources[fixture_id]
        candidate = candidates[profile_id]
        attack = attacks[attack_id]
        expected_provenance = {
            "schema_version": 1,
            "algorithm_version": 2,
            "corpus_contract_sha256": plan.corpus_contract_sha256,
            "profile_contract_sha256": plan.profile_contract_sha256,
            "attack_matrix_sha256": plan.attack_matrix_sha256,
            "benchmark_plan_sha256": plan.plan_sha256,
            "candidate_id": candidate.candidate_id,
            "fixture_kind": source.kind,
            "attack_kind": attack.kind,
            "attack_parameters": dict(attack.parameters),
            "seed": plan.seed,
            "canonical_shape": [canvas_height, canvas_width],
        }
        for field, expected in expected_provenance.items():
            if row.get(field) != expected:
                raise ValueError(f"pre-gate row provenance mismatch for {field}")
        expected_id = None
        if source.kind != "negative_external":
            expected_id = str(_case_context(plan.seed, fixture_id, page_index, profile_id)[0])
        if row.get("expected_id") != expected_id:
            raise ValueError("pre-gate expected issuance identity mismatch")
        reason = _required_string(row, "reason")
        status = _required_string(row, "algorithm_status")
        if reason == "execution_error":
            if status != "execution_error":
                raise ValueError("execution-error row status mismatch")
        else:
            expected_reason = {
                "decoded": "decoded",
                "partial_payload_evidence": "partial",
                "payload_not_detected": "not_detected",
                "insufficient_sync_evidence": "not_detected",
                "geometry_rejected": "not_detected",
            }.get(status)
            if expected_reason != reason:
                raise ValueError("V2 evidence status and generic row reason disagree")
        decoded = row.get("decoded_id")
        if status != "decoded" and decoded is not None:
            raise ValueError("non-decoded V2 status exposes an issuance identity")
        if reason != "execution_error":
            _validate_crop_eligibility(
                row,
                plan,
                candidate,
                attack,
                expected_id,
                (canvas_height, canvas_width),
            )
    if require_complete and observed != expected_set:
        raise ValueError("pre-gate results contain missing scheduled rows")


def _validate_crop_eligibility(
    row: Mapping[str, object],
    plan: ExecutionPlan,
    candidate: Candidate,
    attack: AttackCase,
    expected_id: str | None,
    page_shape: tuple[int, int],
) -> None:
    expected: tuple[bool, int | None, str] = (True, None, "eligible")
    if expected_id is not None and attack.case_id == "crop-f0p25":
        height, width = page_shape
        side_scale = math.sqrt(0.75)
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
        _, key, _ = _case_context(
            plan.seed,
            _required_string(row, "fixture_id"),
            page_index,
            candidate.profile_sha256,
        )
        profile = next(
            profile
            for profile in load_v2_profiles()
            if candidate_identifier_v2(profile).hex() == candidate.candidate_id
        )
        remaining = _remaining_embedded_tiles_v2(
            page_shape, key, page_index, profile, retained
        )
        eligible = remaining >= 2
        expected = (
            eligible,
            remaining,
            "at_least_two_complete_embedded_tiles_remain"
            if eligible
            else "fewer_than_two_complete_embedded_tiles_remain",
        )
    actual = (
        row.get("eligible"),
        row.get("remaining_embedded_tiles"),
        row.get("eligibility_reason"),
    )
    if actual != expected:
        raise ValueError("pre-gate crop eligibility was tampered")


def _qualified_ids(summary: PreGateSummaryV2) -> tuple[str, ...]:
    if (
        summary.status != "complete"
        or summary.completed_rows != REQUIRED_ROWS
        or summary.execution_errors != 0
    ):
        return ()
    return tuple(
        sorted(score.candidate_id for score in summary.candidates if _score_passes(score))
    )


def _score_passes(score: PreGateCandidateScoreV2) -> bool:
    return (
        score.scheduled_rows == 88
        and score.execution_errors == 0
        and score.false_attribution == 0
        and score.jpeg70_denominator == 12
        and score.jpeg70_rate is not None
        and score.jpeg70_rate >= 0.95
        and score.resize075_denominator == 12
        and score.resize075_rate is not None
        and score.resize075_rate >= 0.95
        and score.crop025_denominator > 0
        and score.crop025_rate is not None
        and score.crop025_rate >= 0.90
        and score.quality_observations == 12
        and score.mean_psnr_db is not None
        and score.mean_psnr_db >= 38.0
        and score.mean_ssim is not None
        and score.mean_ssim >= 0.95
        and score.gradient_completed_attacks == 4
        and not score.failed_gates
    )


def _decode_counts(rows: Sequence[Mapping[str, object]]) -> tuple[int, int]:
    return (
        sum(
            row.get("reason") != "execution_error"
            and row.get("decoded_id") == row.get("expected_id")
            for row in rows
        ),
        len(rows),
    )


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _contract_hashes(plan: ExecutionPlan) -> dict[str, str]:
    return {
        "corpus_sha256": plan.corpus_contract_sha256,
        "profiles_sha256": plan.profile_contract_sha256,
        "attack_matrix_sha256": plan.attack_matrix_sha256,
    }


def _summary_document(summary: PreGateSummaryV2) -> dict[str, object]:
    return {
        "schema_version": 2,
        "status": summary.status,
        "evidence_scope": "research_measurement_only",
        "profile_promoted": False,
        "planned_rows": summary.planned_rows,
        "completed_rows": summary.completed_rows,
        "execution_errors": summary.execution_errors,
        "contract_hashes": dict(summary.contract_hashes),
        "plan_sha256": summary.plan_sha256,
        "results_sha256": summary.results_sha256,
        "qualified_candidate_ids": list(summary.qualified_candidate_ids),
        "candidates": [
            json.loads(_canonical_json(asdict(score))) for score in summary.candidates
        ],
        "limitations": list(summary.limitations),
    }


def _decode_json_lines(content: bytes) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        if not line.strip():
            raise ValueError(f"results JSONL contains blank line {line_number}")
        rows.append(_decode_json_object(line, f"result row {line_number}"))
    return rows


def _decode_json_object(content: bytes, label: str) -> dict[str, object]:
    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"{label} contains duplicate JSON key: {key}")
            value[key] = item
        return value

    try:
        value = json.loads(content, object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _required_status(document: Mapping[str, object]) -> Literal[
    "complete", "complete_with_errors", "incomplete"
]:
    value = document.get("status")
    if value not in {"complete", "complete_with_errors", "incomplete"}:
        raise ValueError("pre-gate summary status is invalid")
    return value  # type: ignore[return-value]


def _required_contract_hashes(document: Mapping[str, object]) -> dict[str, str]:
    value = document.get("contract_hashes")
    if not isinstance(value, Mapping) or set(value) != {
        "corpus_sha256",
        "profiles_sha256",
        "attack_matrix_sha256",
    }:
        raise ValueError("pre-gate contract hashes are invalid")
    return {field: _required_sha256(value, field) for field in value}


def _required_sha256(document: Mapping[str, object], field: str) -> str:
    value = _required_string(document, field)
    if len(value) != 64:
        raise ValueError(f"{field} must be a SHA-256 hexadecimal digest")
    try:
        bytes.fromhex(value)
    except ValueError as error:
        raise ValueError(f"{field} must be a SHA-256 hexadecimal digest") from error
    return value


def _required_string(document: Mapping[str, object], field: str) -> str:
    value = document.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _required_integer(document: Mapping[str, object], field: str) -> int:
    value = document.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def _required_number(document: Mapping[str, object], field: str) -> float:
    value = document.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field} must be a finite number")
    return result


def _required_string_tuple(
    document: Mapping[str, object], field: str
) -> tuple[str, ...]:
    value = document.get(field)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{field} must be a string array")
    return tuple(value)
