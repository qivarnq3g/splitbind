"""Deterministic, hash-bound, fail-closed fingerprint V3 pre-gate evidence."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Literal, Mapping, Sequence

from splitbind_attack.attacks import AttackCase, planned_crop_geometry
from splitbind_ref.contracts import fingerprint_candidates_v3, fingerprint_candidates_v3_bytes
from splitbind_ref.fingerprint_v3_profile import candidate_identifier_v3, load_v3_profiles

from .pregate_v2 import (
    _same_json_value,
    _validate_limitations,
    _validate_measurement_fields,
    _validate_reconstructed_attack_evidence,
)
from .runner import (
    Candidate,
    ExecutionPlan,
    _atomic_write_text,
    _benchmark_dimensions,
    _canonical_json,
    _case_context,
    _case_seed,
    _outcome,
    _plan_digest,
    _remaining_embedded_tiles_v3,
    _row_identifier,
    _run_execution_plan,
    build_execution_plan,
)


ROOT = Path(__file__).resolve().parents[4]
DEFAULT_CORPUS = ROOT / "fixtures" / "corpus" / "corpus-manifest.v1.json"
DEFAULT_MATRIX = ROOT / "contracts" / "algorithm" / "attack-matrix.v1.json"
REQUIRED_SEED = 20260905
REQUIRED_POSITIVE_PAGES = 12
REQUIRED_NEGATIVE_PAGES = 10
REQUIRED_CANDIDATES = 4
REQUIRED_ATTACKS = 4
REQUIRED_ROWS = 352
_REQUIRED_ATTACK_IDS = ("identity", "jpeg-q70", "resize-s0p75", "crop-f0p25")
_V3_ROW_FIELDS = frozenset(
    {
        "schema_version", "row_id", "evidence_scope", "profile_promoted",
        "corpus_contract_sha256", "corpus_sha256", "profile_contract_sha256",
        "attack_matrix_sha256", "benchmark_plan_sha256", "algorithm_profile_sha256",
        "candidate_id", "fixture_id", "fixture_kind", "page_index", "attack_id",
        "attack_kind", "attack_parameters", "ordered_operations", "seed", "case_seed",
        "expected_id", "decoded_id", "confidence", "bit_error_rate", "reason", "outcome",
        "valid_vote_count", "psnr_db", "ssim", "quality_data_range", "quality_scope",
        "localization_iou", "tamper_ground_truth", "ground_truth_coordinate_system",
        "elapsed_ms", "timing_scope", "peak_rss_bytes", "peak_rss_scope",
        "temp_peak_bytes", "temp_peak_scope", "eligible", "eligibility_reason",
        "remaining_embedded_tiles", "removed_area_fraction", "limitations",
        "algorithm_version", "algorithm_status", "canonical_shape",
    }
)


@dataclass(frozen=True, slots=True)
class PreGateCandidateScoreV3:
    profile_id: str
    candidate_id: str
    scheduled_rows: int
    execution_errors: int
    false_attributions: int
    jpeg70_true_attributions: int
    jpeg70_denominator: int
    jpeg70_decode_rate: float | None
    resize075_true_attributions: int
    resize075_denominator: int
    resize075_decode_rate: float | None
    crop025_true_attributions: int
    crop025_denominator: int
    crop025_decode_rate: float | None
    quality_observations: int
    minimum_psnr_db: float | None
    minimum_ssim: float | None
    failed_gates: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PreGateSummaryV3:
    status: Literal["complete", "complete_with_errors", "incomplete"]
    planned_rows: int
    completed_rows: int
    execution_errors: int
    false_attributions: int
    contract_hashes: Mapping[str, str]
    plan_sha256: str
    results_sha256: str
    qualified_candidate_ids: tuple[str, ...]
    candidates: tuple[PreGateCandidateScoreV3, ...]
    limitations: tuple[str, ...]


def build_v3_pregate_plan(
    corpus: str | Path,
    profiles: str | Path,
    matrix: str | Path,
    seed: int,
    *,
    smoke: bool = False,
) -> ExecutionPlan:
    """Build the bounded V3 population with the four exact pre-gate attacks."""

    full = build_execution_plan(corpus, profiles, matrix, seed, smoke=smoke)
    if full.algorithm_version != 3:
        raise ValueError("V3 pre-gate requires a schema_version 3 candidate contract")
    all_attacks = build_execution_plan(corpus, profiles, matrix, seed).attacks
    by_id = {attack.case_id: attack for attack in all_attacks}
    try:
        selected = (
            AttackCase("identity", "identity", {}),
            by_id["jpeg-q70"],
            by_id["resize-s0p75"],
            by_id["crop-f0p25"],
        )
    except KeyError as error:
        raise ValueError("attack matrix is missing an exact V3 pre-gate attack") from error
    actual = tuple((case.case_id, case.kind, dict(case.parameters)) for case in selected)
    expected = (
        ("identity", "identity", {}),
        ("jpeg-q70", "jpeg", {"quality": 70}),
        ("resize-s0p75", "resize", {"scale": 0.75}),
        ("crop-f0p25", "crop", {"fraction": 0.25}),
    )
    if actual != expected:
        raise ValueError("attack matrix does not contain the unchanged V3 pre-gate attacks")
    if not smoke and (
        full.positive_pages,
        full.negative_pages,
        full.candidate_count,
    ) != (REQUIRED_POSITIVE_PAGES, REQUIRED_NEGATIVE_PAGES, REQUIRED_CANDIDATES):
        raise ValueError("corpus and V3 contract do not form the exact pre-gate population")
    if full.candidate_count > 16:
        raise ValueError("V3 pre-gate exceeds the 16-candidate ceiling")
    planned_rows = full.corpus_pages * full.candidate_count * len(selected)
    return replace(
        full,
        attacks=selected,
        attack_count=len(selected),
        planned_rows=planned_rows,
        plan_sha256=_plan_digest(full.sources, full.candidates, selected),
        run_kind="v3_pregate",
    )


def run_v3_pregate(
    corpus: str | Path,
    profiles: str | Path,
    matrix: str | Path,
    seed: int,
    output_dir: str | Path,
    *,
    smoke: bool = False,
    max_rows: int | None = None,
) -> PreGateSummaryV3:
    """Run/resume V3 rows, validate them, and publish the selection last."""

    plan = build_v3_pregate_plan(corpus, profiles, matrix, seed, smoke=smoke)
    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    selection_path = destination / "qualified-candidate-ids.json"
    _atomic_write_text(selection_path, _selection_text(plan, "0" * 64, "0" * 64, ()))
    _run_execution_plan(plan, destination, max_rows=max_rows)
    results_path = destination / "results.jsonl"
    results_bytes = results_path.read_bytes()
    rows = _decode_json_lines(results_bytes)
    _validate_rows(rows, plan, require_complete=False)
    scores = _aggregate_scores(rows, plan)
    status, completed, errors, false_attributions = _evidence_state(rows, plan.planned_rows)
    preliminary = PreGateSummaryV3(
        status=status,
        planned_rows=plan.planned_rows,
        completed_rows=completed,
        execution_errors=errors,
        false_attributions=false_attributions,
        contract_hashes=_contract_hashes(plan),
        plan_sha256=plan.plan_sha256,
        results_sha256=hashlib.sha256(results_bytes).hexdigest(),
        qualified_candidate_ids=(),
        candidates=scores,
        limitations=(
            "The V3 pre-gate is a deterministic cost-control filter, not release evidence.",
            "Only identity, JPEG 70, resize 0.75, and center crop 0.25 are measured.",
            "Only a complete full population can produce qualified candidate identifiers.",
        ),
    )
    qualified = _qualified_ids(preliminary) if not smoke else ()
    summary = replace(preliminary, qualified_candidate_ids=qualified)
    summary_text = json.dumps(_summary_document(summary), indent=2, sort_keys=True, allow_nan=False) + "\n"
    _atomic_write_text(destination / "summary.json", summary_text)
    _atomic_write_text(
        selection_path,
        _selection_text(
            plan,
            summary.results_sha256,
            hashlib.sha256(summary_text.encode("utf-8")).hexdigest(),
            qualified,
        ),
    )
    return summary


def select_qualified_candidates_v3(
    summary: PreGateSummaryV3, contract: Mapping[str, object]
) -> tuple[bytes, ...]:
    """Validate full V3 evidence and return exact binary candidate identifiers."""

    if not isinstance(summary, PreGateSummaryV3):
        raise TypeError("summary must be a PreGateSummaryV3")
    if not isinstance(contract, Mapping) or dict(contract) != fingerprint_candidates_v3():
        raise ValueError("V3 selection requires the exact frozen source contract")
    expected_hash = hashlib.sha256(fingerprint_candidates_v3_bytes()).hexdigest()
    if summary.contract_hashes.get("profiles_sha256") != expected_hash:
        raise ValueError("pre-gate source contract hash mismatch")
    if summary.planned_rows != REQUIRED_ROWS:
        raise ValueError("pre-gate summary planned row count mismatch")
    _validate_candidate_score_population(summary.candidates)
    if (
        summary.status != "complete"
        or summary.completed_rows != REQUIRED_ROWS
        or summary.execution_errors != 0
        or summary.false_attributions != 0
        or any(score.execution_errors or score.false_attributions for score in summary.candidates)
    ):
        return ()
    if any(not _score_passes(score) for score in summary.candidates):
        return ()
    expected = _qualified_ids(summary)
    if tuple(summary.qualified_candidate_ids) != expected:
        raise ValueError("pre-gate qualified candidate list disagrees with measured gates")
    available = {candidate_identifier_v3(profile) for profile in load_v3_profiles()}
    selected = tuple(bytes.fromhex(candidate_id) for candidate_id in expected)
    if any(candidate_id not in available for candidate_id in selected):
        raise ValueError("pre-gate qualified list contains an unknown candidate")
    return selected


def load_v3_pregate_summary(
    summary: str | Path,
    profiles: str | Path,
    *,
    corpus: str | Path = DEFAULT_CORPUS,
    matrix: str | Path = DEFAULT_MATRIX,
) -> PreGateSummaryV3:
    """Reconstruct every aggregate from sibling row evidence and pinned inputs."""

    summary_path = Path(summary).resolve()
    document = _decode_json_object(summary_path.read_bytes(), "pre-gate summary")
    results_bytes = summary_path.with_name("results.jsonl").read_bytes()
    rows = _decode_json_lines(results_bytes)
    plan = build_v3_pregate_plan(corpus, profiles, matrix, REQUIRED_SEED)
    _validate_rows(rows, plan, require_complete=True)
    scores = _aggregate_scores(rows, plan)
    status, completed, errors, false_attributions = _evidence_state(rows, REQUIRED_ROWS)
    evidence = PreGateSummaryV3(
        status=status,
        planned_rows=REQUIRED_ROWS,
        completed_rows=completed,
        execution_errors=errors,
        false_attributions=false_attributions,
        contract_hashes=_required_contract_hashes(document),
        plan_sha256=_required_sha256(document, "plan_sha256"),
        results_sha256=_required_sha256(document, "results_sha256"),
        qualified_candidate_ids=_required_string_tuple(document, "qualified_candidate_ids"),
        candidates=scores,
        limitations=_required_string_tuple(document, "limitations"),
    )
    if document != _summary_document(evidence):
        raise ValueError("pre-gate summary fields or candidate aggregates were tampered")
    if evidence.contract_hashes != _contract_hashes(plan):
        raise ValueError("pre-gate summary contract hashes mismatch")
    if evidence.plan_sha256 != plan.plan_sha256:
        raise ValueError("pre-gate summary plan hash mismatch")
    if evidence.results_sha256 != hashlib.sha256(results_bytes).hexdigest():
        raise ValueError("pre-gate results hash mismatch")
    select_qualified_candidates_v3(evidence, fingerprint_candidates_v3())
    return evidence


def load_qualified_candidate_selection_v3(
    selection: str | Path, profiles: str | Path
) -> tuple[bytes, ...]:
    """Validate an atomic V3 selection against its summary and result bytes."""

    selection_path = Path(selection).resolve()
    document = _decode_json_object(selection_path.read_bytes(), "candidate selection")
    expected_fields = {
        "schema_version", "source_contract_sha256", "pregate_plan_sha256",
        "pregate_results_sha256", "pregate_summary_sha256", "qualified_candidate_ids",
    }
    if set(document) != expected_fields or document.get("schema_version") != 3:
        raise ValueError("candidate selection must contain the exact V3 evidence fields")
    profile_path = Path(profiles).resolve()
    if document.get("source_contract_sha256") != hashlib.sha256(profile_path.read_bytes()).hexdigest():
        raise ValueError("candidate selection source contract hash mismatch")
    ids = _required_string_tuple(document, "qualified_candidate_ids")
    if tuple(sorted(set(ids))) != ids:
        raise ValueError("qualified candidate identifiers must be sorted and unique")
    summary_bytes = selection_path.with_name("summary.json").read_bytes()
    results_bytes = selection_path.with_name("results.jsonl").read_bytes()
    if document.get("pregate_summary_sha256") != hashlib.sha256(summary_bytes).hexdigest():
        raise ValueError("candidate selection summary hash mismatch")
    if document.get("pregate_results_sha256") != hashlib.sha256(results_bytes).hexdigest():
        raise ValueError("candidate selection results hash mismatch")
    evidence = load_v3_pregate_summary(selection_path.with_name("summary.json"), profile_path)
    if document.get("pregate_plan_sha256") != evidence.plan_sha256:
        raise ValueError("candidate selection plan hash mismatch")
    selected = select_qualified_candidates_v3(evidence, fingerprint_candidates_v3())
    if tuple(value.hex() for value in selected) != ids:
        raise ValueError("candidate selection identifiers were tampered")
    return selected


def _aggregate_scores(
    rows: Sequence[Mapping[str, object]], plan: ExecutionPlan
) -> tuple[PreGateCandidateScoreV3, ...]:
    grouped = {candidate.profile_sha256: [] for candidate in plan.candidates}
    for row in rows:
        profile_id = _required_string(row, "algorithm_profile_sha256")
        if profile_id not in grouped:
            raise ValueError("result row contains an unknown V3 profile")
        grouped[profile_id].append(row)
    candidates = {candidate.profile_sha256: candidate for candidate in plan.candidates}
    return tuple(
        _aggregate_one(candidates[profile_id], grouped[profile_id])
        for profile_id in sorted(grouped)
    )


def _aggregate_one(
    candidate: Candidate, rows: Sequence[Mapping[str, object]]
) -> PreGateCandidateScoreV3:
    if rows and {_required_string(row, "candidate_id") for row in rows} != {candidate.candidate_id}:
        raise ValueError("candidate rows contain inconsistent candidate identity")
    errors = sum(row.get("reason") == "execution_error" for row in rows)
    false_attributions = sum(
        row.get("decoded_id") is not None and row.get("decoded_id") != row.get("expected_id")
        for row in rows
    )
    required = {attack_id: [] for attack_id in _REQUIRED_ATTACK_IDS[1:]}
    quality: dict[tuple[str, int], tuple[float, float]] = {}
    for row in rows:
        if row.get("expected_id") is None:
            continue
        attack_id = _required_string(row, "attack_id")
        if attack_id in required:
            required[attack_id].append(row)
        if row.get("reason") != "execution_error":
            observation = (_psnr_number(row.get("psnr_db")), _required_number(row, "ssim"))
            key = (_required_string(row, "fixture_id"), _required_integer(row, "page_index"))
            previous = quality.setdefault(key, observation)
            if previous != observation:
                raise ValueError("repeated quality observations disagree")
    jpeg_true, jpeg_denominator = _decode_counts(required["jpeg-q70"])
    resize_true, resize_denominator = _decode_counts(required["resize-s0p75"])
    crop_rows = [row for row in required["crop-f0p25"] if row.get("eligible") is True]
    crop_true, crop_denominator = _decode_counts(crop_rows)
    jpeg_rate = _rate(jpeg_true, jpeg_denominator)
    resize_rate = _rate(resize_true, resize_denominator)
    crop_rate = _rate(crop_true, crop_denominator)
    minimum_psnr = min((value[0] for value in quality.values()), default=None)
    minimum_ssim = min((value[1] for value in quality.values()), default=None)
    failed: list[str] = []
    if errors:
        failed.append("execution_errors_zero")
    if false_attributions:
        failed.append("false_attributions_zero")
    if jpeg_rate is None or jpeg_rate < 0.95:
        failed.append("jpeg70_decode_rate_at_least_0.95")
    if resize_rate is None or resize_rate < 0.95:
        failed.append("resize075_decode_rate_at_least_0.95")
    if crop_rate is None or crop_rate < 0.90:
        failed.append("crop025_decode_rate_at_least_0.90")
    if minimum_psnr is None or minimum_psnr < 38.0:
        failed.append("minimum_psnr_db_at_least_38")
    if minimum_ssim is None or minimum_ssim < 0.95:
        failed.append("minimum_ssim_at_least_0.95")
    if len(quality) != REQUIRED_POSITIVE_PAGES:
        failed.append("complete_quality_population_12")
    return PreGateCandidateScoreV3(
        profile_id=candidate.profile_sha256,
        candidate_id=candidate.candidate_id or "",
        scheduled_rows=len(rows),
        execution_errors=errors,
        false_attributions=false_attributions,
        jpeg70_true_attributions=jpeg_true,
        jpeg70_denominator=jpeg_denominator,
        jpeg70_decode_rate=jpeg_rate,
        resize075_true_attributions=resize_true,
        resize075_denominator=resize_denominator,
        resize075_decode_rate=resize_rate,
        crop025_true_attributions=crop_true,
        crop025_denominator=crop_denominator,
        crop025_decode_rate=crop_rate,
        quality_observations=len(quality),
        minimum_psnr_db=minimum_psnr,
        minimum_ssim=minimum_ssim,
        failed_gates=tuple(failed),
    )
def _validate_rows(
    rows: Sequence[Mapping[str, object]], plan: ExecutionPlan, *, require_complete: bool
) -> None:
    if len(rows) > plan.planned_rows or (require_complete and len(rows) != plan.planned_rows):
        raise ValueError("pre-gate results contain a missing or excess row population")
    sources = {source.fixture_id: source for source in plan.sources}
    candidates = {candidate.profile_sha256: candidate for candidate in plan.candidates}
    attacks = {attack.case_id: attack for attack in plan.attacks}
    expected_set = {
        (source.fixture_id, page_index, candidate.profile_sha256, attack.case_id)
        for source in plan.sources
        for page_index in range(source.pages)
        for candidate in plan.candidates
        for attack in plan.attacks
    }
    observed: set[tuple[str, int, str, str]] = set()
    row_ids: set[str] = set()
    canvas_width, canvas_height = _benchmark_dimensions(plan.candidates)
    artifacts = {}
    canvas_transforms = {}
    for ordinal, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"pre-gate row {ordinal} must be an object")
        _validate_exact_row_fields(row, ordinal)
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
        if row_id in row_ids or row_id != _row_identifier(*key):
            raise ValueError("pre-gate row identity is duplicate or invalid")
        row_ids.add(row_id)
        source = sources[fixture_id]
        candidate = candidates[profile_id]
        attack = attacks[attack_id]
        provenance = {
            "schema_version": 1,
            "algorithm_version": 3,
            "evidence_scope": "research_measurement_only",
            "profile_promoted": False,
            "corpus_contract_sha256": plan.corpus_contract_sha256,
            "corpus_sha256": source.sha256,
            "profile_contract_sha256": plan.profile_contract_sha256,
            "attack_matrix_sha256": plan.attack_matrix_sha256,
            "benchmark_plan_sha256": plan.plan_sha256,
            "algorithm_profile_sha256": candidate.profile_sha256,
            "candidate_id": candidate.candidate_id,
            "fixture_kind": source.kind,
            "attack_kind": attack.kind,
            "attack_parameters": dict(attack.parameters),
            "ordered_operations": [operation.kind for operation in attack.operations]
            if attack.operations else [attack.kind],
            "seed": plan.seed,
            "case_seed": _case_seed(plan.seed, fixture_id, page_index, profile_id, attack_id),
            "canonical_shape": [canvas_height, canvas_width],
        }
        for field, expected in provenance.items():
            if not _same_json_value(row.get(field), expected):
                raise ValueError(f"pre-gate row provenance mismatch for {field}")
        _validate_measurement_fields(row, source.kind)
        expected_id = None if source.kind == "negative_external" else str(
            _case_context(plan.seed, fixture_id, page_index, profile_id)[0]
        )
        if row.get("expected_id") != expected_id:
            raise ValueError("pre-gate expected issuance identity mismatch")
        reason = _required_string(row, "reason")
        status = _required_string(row, "algorithm_status")
        expected_reason = {
            "decoded": "decoded",
            "partial_payload_evidence": "partial",
            "conflicting_payload_evidence": "not_detected",
            "payload_not_detected": "not_detected",
            "insufficient_sync_evidence": "not_detected",
            "geometry_rejected": "not_detected",
            "execution_error": "execution_error",
        }.get(status)
        if expected_reason != reason:
            raise ValueError("V3 evidence status and generic row reason disagree")
        decoded = row.get("decoded_id")
        if status != "decoded" and decoded is not None:
            raise ValueError("non-decoded V3 status exposes an issuance identity")
        if status == "decoded":
            _validate_canonical_uuid(decoded, "decoded_id")
        _validate_v3_evidence_values(row, candidate, status)
        artifact_absent = _validate_limitations(row, reason)
        expected_outcome = _outcome(
            expected_id,
            decoded if isinstance(decoded, str) else None,
            reason,
            "execution_error" if reason == "execution_error" else None,
        )
        if row.get("outcome") != expected_outcome:
            raise ValueError("pre-gate row outcome disagrees with the evidence state")
        _validate_crop_eligibility(row, plan, candidate, attack, expected_id, (canvas_height, canvas_width))
        _validate_reconstructed_attack_evidence(
            row, source, page_index, attack, (canvas_height, canvas_width),
            artifact_absent, artifacts, canvas_transforms,
        )
    if require_complete and observed != expected_set:
        raise ValueError("pre-gate results contain missing scheduled rows")


def _validate_exact_row_fields(row: Mapping[str, object], ordinal: int) -> None:
    if set(row) == _V3_ROW_FIELDS:
        return
    unexpected = sorted(set(row) - _V3_ROW_FIELDS)
    missing = sorted(_V3_ROW_FIELDS - set(row))
    details = ([f"unexpected fields {unexpected}"] if unexpected else []) + (
        [f"missing fields {missing}"] if missing else []
    )
    raise ValueError(f"pre-gate row {ordinal} has " + "; ".join(details))


def _validate_v3_evidence_values(
    row: Mapping[str, object], candidate: Candidate, status: str
) -> None:
    votes = _required_integer(row, "valid_vote_count")
    repetitions = int(candidate.values["payload_repetitions"])
    if votes > repetitions:
        raise ValueError("valid_vote_count exceeds the candidate repetition bound")
    ber = row.get("bit_error_rate")
    if status == "decoded":
        if votes < 2 or ber is None:
            raise ValueError("decoded V3 evidence requires at least two votes and BER")
    elif status in {"partial_payload_evidence", "conflicting_payload_evidence"}:
        if votes < 1 or ber is None:
            raise ValueError("payload-bearing V3 evidence requires at least one vote and BER")
    elif votes != 0 or ber is not None:
        raise ValueError("non-payload V3 evidence must not carry payload votes or BER")


def _validate_crop_eligibility(
    row: Mapping[str, object], plan: ExecutionPlan, candidate: Candidate,
    attack: AttackCase, expected_id: str | None, page_shape: tuple[int, int],
) -> None:
    expected: tuple[bool, int | None, str] = (True, None, "eligible")
    if expected_id is not None and attack.case_id == "crop-f0p25":
        planned = planned_crop_geometry(attack, page_shape)
        if planned is None:
            raise ValueError("pre-gate crop attack geometry is unavailable")
        page_index = _required_integer(row, "page_index")
        _, key, _ = _case_context(
            plan.seed, _required_string(row, "fixture_id"), page_index, candidate.profile_sha256
        )
        profile = next(
            profile for profile in load_v3_profiles()
            if candidate_identifier_v3(profile).hex() == candidate.candidate_id
        )
        remaining = _remaining_embedded_tiles_v3(page_shape, key, page_index, profile, planned[0])
        eligible = remaining >= 2
        expected = (
            eligible, remaining,
            "at_least_two_complete_embedded_tiles_remain"
            if eligible else "fewer_than_two_complete_embedded_tiles_remain",
        )
    actual = (row.get("eligible"), row.get("remaining_embedded_tiles"), row.get("eligibility_reason"))
    if actual != expected:
        raise ValueError("pre-gate crop eligibility was tampered")


def _validate_candidate_score_population(scores: Sequence[PreGateCandidateScoreV3]) -> None:
    expected = {
        hashlib.sha256(candidate_identifier_v3(profile)).hexdigest(): candidate_identifier_v3(profile).hex()
        for profile in load_v3_profiles()
    }
    if len(scores) != REQUIRED_CANDIDATES:
        raise ValueError("pre-gate summary must contain exactly 4 candidate scores")
    observed: dict[str, str] = {}
    for score in scores:
        if not isinstance(score, PreGateCandidateScoreV3) or score.profile_id in observed:
            raise ValueError("pre-gate candidate score population is invalid")
        if score.scheduled_rows != REQUIRED_ROWS // REQUIRED_CANDIDATES:
            raise ValueError("pre-gate candidate score must cover exactly 88 rows")
        if (
            score.jpeg70_denominator != REQUIRED_POSITIVE_PAGES
            or score.resize075_denominator != REQUIRED_POSITIVE_PAGES
            or score.crop025_denominator <= 0
            or score.quality_observations != REQUIRED_POSITIVE_PAGES
        ):
            raise ValueError("pre-gate candidate score denominator population is invalid")
        observed[score.profile_id] = score.candidate_id
    if observed != expected:
        raise ValueError("pre-gate summary candidate scores are not the canonical V3 population")


def _score_passes(score: PreGateCandidateScoreV3) -> bool:
    return (
        score.jpeg70_decode_rate is not None
        and score.jpeg70_decode_rate >= 0.95
        and score.resize075_decode_rate is not None
        and score.resize075_decode_rate >= 0.95
        and score.crop025_decode_rate is not None
        and score.crop025_decode_rate >= 0.90
        and score.false_attributions == 0
        and score.execution_errors == 0
        and score.minimum_psnr_db is not None
        and score.minimum_psnr_db >= 38.0
        and score.minimum_ssim is not None
        and score.minimum_ssim >= 0.95
    )


def _qualified_ids(summary: PreGateSummaryV3) -> tuple[str, ...]:
    if (
        summary.status != "complete" or summary.planned_rows != REQUIRED_ROWS
        or summary.completed_rows != REQUIRED_ROWS or summary.execution_errors != 0
        or summary.false_attributions != 0
    ):
        return ()
    if any(not _score_passes(score) for score in summary.candidates):
        return ()
    return tuple(sorted(score.candidate_id for score in summary.candidates))


def _evidence_state(rows: Sequence[Mapping[str, object]], planned_rows: int):
    errors = sum(row.get("reason") == "execution_error" for row in rows)
    false_attributions = sum(row.get("outcome") == "false_attribution" for row in rows)
    status = (
        "complete_with_errors" if len(rows) == planned_rows and errors
        else "complete" if len(rows) == planned_rows else "incomplete"
    )
    return status, len(rows), errors, false_attributions


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


def _psnr_number(value: object) -> float:
    if value == "Infinity":
        return math.inf
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError("psnr_db must be finite or Infinity")
    return float(value)


def _contract_hashes(plan: ExecutionPlan) -> dict[str, str]:
    return {
        "corpus_sha256": plan.corpus_contract_sha256,
        "profiles_sha256": plan.profile_contract_sha256,
        "attack_matrix_sha256": plan.attack_matrix_sha256,
    }


def _summary_document(summary: PreGateSummaryV3) -> dict[str, object]:
    return {
        "schema_version": 3,
        "status": summary.status,
        "evidence_scope": "research_measurement_only",
        "profile_promoted": False,
        "planned_rows": summary.planned_rows,
        "completed_rows": summary.completed_rows,
        "execution_errors": summary.execution_errors,
        "false_attributions": summary.false_attributions,
        "contract_hashes": dict(summary.contract_hashes),
        "plan_sha256": summary.plan_sha256,
        "results_sha256": summary.results_sha256,
        "qualified_candidate_ids": list(summary.qualified_candidate_ids),
        "candidates": [json.loads(_canonical_json(asdict(score))) for score in summary.candidates],
        "limitations": list(summary.limitations),
    }


def _selection_text(
    plan: ExecutionPlan, results_sha256: str, summary_sha256: str,
    qualified: Sequence[str],
) -> str:
    return json.dumps(
        {
            "schema_version": 3,
            "source_contract_sha256": plan.profile_contract_sha256,
            "pregate_plan_sha256": plan.plan_sha256,
            "pregate_results_sha256": results_sha256,
            "pregate_summary_sha256": summary_sha256,
            "qualified_candidate_ids": list(qualified),
        },
        indent=2,
        sort_keys=True,
    ) + "\n"


def _decode_json_lines(content: bytes) -> list[dict[str, object]]:
    rows = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        if not line.strip():
            raise ValueError(f"results JSONL contains blank line {line_number}")
        rows.append(_decode_json_object(line, f"result row {line_number}"))
    return rows


def _decode_json_object(content: bytes, label: str) -> dict[str, object]:
    def reject_duplicates(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"{label} contains duplicate JSON key: {key}")
            value[key] = item
        return value

    def reject_nonfinite(value: str):
        raise ValueError(f"{label} contains non-finite JSON number: {value}")

    try:
        value = json.loads(
            content,
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_nonfinite,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _required_contract_hashes(document: Mapping[str, object]) -> dict[str, str]:
    value = document.get("contract_hashes")
    expected = {"corpus_sha256", "profiles_sha256", "attack_matrix_sha256"}
    if not isinstance(value, Mapping) or set(value) != expected:
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


def _required_string_tuple(document: Mapping[str, object], field: str) -> tuple[str, ...]:
    value = document.get(field)
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{field} must be a string array")
    return tuple(value)


def _validate_canonical_uuid(value: object, field: str) -> None:
    from uuid import UUID

    if not isinstance(value, str):
        raise ValueError(f"{field} must be a canonical UUID string")
    try:
        if str(UUID(value)) != value:
            raise ValueError
    except ValueError as error:
        raise ValueError(f"{field} must be a canonical UUID string") from error
