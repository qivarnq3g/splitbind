import hashlib
import json
import sqlite3
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import cv2

from splitbind_attack.attacks import AttackCase, apply_attack
from splitbind_bench.pregate_v2 import (
    PreGateCandidateScoreV2,
    PreGateSummaryV2,
    build_v2_pregate_plan,
    load_qualified_candidate_selection,
    select_qualified_candidates,
    _validate_rows,
)
from splitbind_bench import runner
from splitbind_bench import pregate_v2
from splitbind_bench.runner import (
    _case_context,
    _case_seed,
    _initialize_checkpoint,
    _row_identifier,
    _run_identity,
)
from splitbind_ref.fingerprint_v2 import DecodeV2Decision
from splitbind_ref.contracts import fingerprint_candidates_v2
from splitbind_ref.fingerprint_v2_profile import candidate_identifier_v2, load_v2_profiles
from splitbind_ref.synchronization_v2 import AlignmentV2RuntimeError


ROOT = Path(__file__).resolve().parents[4]
PROFILES = ROOT / "contracts" / "algorithm" / "fingerprint-candidates.v2.json"
CORPUS = ROOT / "fixtures" / "corpus" / "corpus-manifest.v1.json"
MATRIX = ROOT / "contracts" / "algorithm" / "attack-matrix.v1.json"


def _score_for(profile, **overrides) -> PreGateCandidateScoreV2:
    values = {
        "profile_id": hashlib.sha256(candidate_identifier_v2(profile)).hexdigest(),
        "candidate_id": candidate_identifier_v2(profile).hex(),
        "scheduled_rows": 88,
        "execution_errors": 0,
        "false_attribution": 0,
        "jpeg70_true_attribution": 12,
        "jpeg70_denominator": 12,
        "jpeg70_rate": 1.0,
        "resize075_true_attribution": 12,
        "resize075_denominator": 12,
        "resize075_rate": 1.0,
        "crop025_true_attribution": 12,
        "crop025_denominator": 12,
        "crop025_rate": 1.0,
        "quality_observations": 12,
        "mean_psnr_db": 38.0,
        "mean_ssim": 0.95,
        "gradient_completed_attacks": 4,
        "failed_gates": (),
    }
    values.update(overrides)
    return PreGateCandidateScoreV2(**values)


def _score(**overrides) -> PreGateCandidateScoreV2:
    return _score_for(load_v2_profiles()[0], **overrides)


def _canonical_scores(
    *, first_only: bool = False, **overrides
) -> tuple[PreGateCandidateScoreV2, ...]:
    profiles = load_v2_profiles()
    return tuple(
        _score_for(profile, **(overrides if not first_only or index == 0 else {}))
        for index, profile in enumerate(profiles)
    )


def _summary(*scores: PreGateCandidateScoreV2, **overrides) -> PreGateSummaryV2:
    values = {
        "status": "complete",
        "planned_rows": 1408,
        "completed_rows": 1408,
        "execution_errors": 0,
        "contract_hashes": {
            "profiles_sha256": hashlib.sha256(PROFILES.read_bytes()).hexdigest(),
            "corpus_sha256": hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
            "attack_matrix_sha256": hashlib.sha256(MATRIX.read_bytes()).hexdigest(),
        },
        "plan_sha256": "1" * 64,
        "results_sha256": "2" * 64,
        "qualified_candidate_ids": tuple(
            sorted(score.candidate_id for score in scores if not score.failed_gates)
        ),
        "candidates": tuple(scores),
        "limitations": (),
    }
    values.update(overrides)
    return PreGateSummaryV2(**values)


def test_v2_pregate_plan_is_exact():
    plan = build_v2_pregate_plan(CORPUS, PROFILES, MATRIX, seed=20260827)

    assert plan.positive_pages == 12
    assert plan.negative_pages == 10
    assert plan.candidate_count == 16
    assert [case.case_id for case in plan.attacks] == [
        "identity",
        "jpeg-q70",
        "resize-s0p75",
        "crop-f0p25",
    ]
    assert plan.planned_rows == 22 * 16 * 4 == 1408


def test_identity_attack_is_a_true_contiguous_copy_without_fabricated_geometry():
    source = np.arange(12 * 16 * 3, dtype=np.uint8).reshape(12, 16, 3)[:, ::-1]
    artifact = apply_attack(
        source,
        AttackCase("identity", "identity", {}),
        np.random.default_rng(20260827),
    )

    assert artifact.image.flags.c_contiguous
    assert np.array_equal(artifact.image, source)
    assert not np.shares_memory(artifact.image, source)
    assert artifact.source_to_output == (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)
    assert artifact.retained_region is None
    assert artifact.ground_truth == ()
    assert artifact.operations == ("identity",)


@pytest.mark.parametrize(
    "summary",
    [
        _summary(*_canonical_scores(), execution_errors=1, status="complete_with_errors"),
        _summary(*_canonical_scores(), completed_rows=1407, status="incomplete"),
    ],
)
def test_any_execution_error_or_incomplete_evidence_empties_the_whole_selection(summary):
    assert select_qualified_candidates(summary, fingerprint_candidates_v2()) == ()


@pytest.mark.parametrize(
    ("field", "value", "failed_gate"),
    [
        ("false_attribution", 1, "false_attribution_zero"),
        ("jpeg70_rate", 0.949, "jpeg70_decode_rate_at_least_0.95"),
        ("resize075_rate", 0.949, "resize075_decode_rate_at_least_0.95"),
        ("crop025_rate", 0.899, "crop025_decode_rate_at_least_0.90"),
        ("mean_psnr_db", 37.999, "mean_psnr_db_at_least_38"),
        ("mean_ssim", 0.949, "mean_ssim_at_least_0.95"),
        ("gradient_completed_attacks", 3, "gradient_completed_all_four_attacks"),
    ],
)
def test_candidate_selection_keeps_the_unchanged_thresholds(field, value, failed_gate):
    scores = _canonical_scores(**{field: value}, failed_gates=(failed_gate,))

    assert select_qualified_candidates(_summary(*scores), fingerprint_candidates_v2()) == ()


def test_selection_is_sorted_by_binary_candidate_identifier():
    scores = tuple(reversed(_canonical_scores()))
    summary = _summary(*scores)

    selected = select_qualified_candidates(summary, fingerprint_candidates_v2())

    assert selected == tuple(sorted(bytes.fromhex(score.candidate_id) for score in scores))


def test_selection_rejects_a_source_contract_hash_mismatch():
    summary = _summary(
        *_canonical_scores(),
        contract_hashes={
            "profiles_sha256": "0" * 64,
            "corpus_sha256": hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
            "attack_matrix_sha256": hashlib.sha256(MATRIX.read_bytes()).hexdigest(),
        },
    )

    with pytest.raises(ValueError, match="contract"):
        select_qualified_candidates(summary, fingerprint_candidates_v2())


def test_selection_loader_rejects_tampering_and_duplicate_json_keys(tmp_path):
    profile = load_v2_profiles()[0]
    candidate_id = candidate_identifier_v2(profile).hex()
    selection = tmp_path / "qualified-candidate-ids.json"
    selection.write_text(
        "{" +
        '"schema_version":2,'
        '"schema_version":2,'
        f'"source_contract_sha256":"{hashlib.sha256(PROFILES.read_bytes()).hexdigest()}",'
        '"pregate_plan_sha256":"' + "1" * 64 + '",'
        '"pregate_results_sha256":"' + "2" * 64 + '",'
        '"pregate_summary_sha256":"' + "3" * 64 + '",'
        f'"qualified_candidate_ids":["{candidate_id}"]' +
        "}",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="duplicate"):
        load_qualified_candidate_selection(selection, PROFILES)


def test_summary_qualified_ids_cannot_disagree_with_candidate_gates():
    scores = _canonical_scores(
        first_only=True,
        mean_ssim=0.94,
        failed_gates=("mean_ssim_at_least_0.95",),
    )
    tampered = _summary(*scores, qualified_candidate_ids=(scores[0].candidate_id,))

    with pytest.raises(ValueError, match="qualified"):
        select_qualified_candidates(tampered, fingerprint_candidates_v2())


def _minimal_valid_row(plan, *, attack_id="identity"):
    source = plan.sources[0]
    candidate = plan.candidates[0]
    attack = next(attack for attack in plan.attacks if attack.case_id == attack_id)
    expected = str(
        _case_context(plan.seed, source.fixture_id, 0, candidate.profile_sha256)[0]
    )
    return {
        "schema_version": 1,
        "algorithm_version": 2,
        "row_id": _row_identifier(
            source.fixture_id, 0, candidate.profile_sha256, attack.case_id
        ),
        "evidence_scope": "research_measurement_only",
        "profile_promoted": False,
        "corpus_contract_sha256": plan.corpus_contract_sha256,
        "corpus_sha256": source.sha256,
        "profile_contract_sha256": plan.profile_contract_sha256,
        "attack_matrix_sha256": plan.attack_matrix_sha256,
        "benchmark_plan_sha256": plan.plan_sha256,
        "algorithm_profile_sha256": candidate.profile_sha256,
        "candidate_id": candidate.candidate_id,
        "fixture_id": source.fixture_id,
        "fixture_kind": source.kind,
        "page_index": 0,
        "attack_id": attack.case_id,
        "attack_kind": attack.kind,
        "attack_parameters": dict(attack.parameters),
        "ordered_operations": [attack.kind],
        "seed": plan.seed,
        "case_seed": _case_seed(
            plan.seed, source.fixture_id, 0, candidate.profile_sha256, attack.case_id
        ),
        "canonical_shape": [1536, 3072],
        "expected_id": expected,
        "decoded_id": None,
        "confidence": 0.0,
        "bit_error_rate": None,
        "reason": "not_detected",
        "algorithm_status": "insufficient_sync_evidence",
        "outcome": "not_detected",
        "valid_vote_count": 0,
        "psnr_db": 40.0,
        "ssim": 1.0,
        "quality_data_range": 255.0,
        "quality_scope": "original_vs_watermarked_before_attack",
        "localization_iou": None,
        "tamper_ground_truth": [],
        "ground_truth_coordinate_system": "normalized_attack_output_axis_aligned_envelope",
        "elapsed_ms": 1.0,
        "timing_scope": "attack_and_decode",
        "peak_rss_bytes": 1,
        "peak_rss_scope": "process_lifetime_high_water_observed_after_attack_and_decode",
        "temp_peak_bytes": 0,
        "temp_peak_scope": "attack_and_decode_in_memory_temporary_files_only",
        "eligible": True,
        "remaining_embedded_tiles": None,
        "eligibility_reason": "eligible",
        "removed_area_fraction": 0.0,
        "limitations": [
            "A5 integrity localization is not implemented; tamper ground truth is recorded but localization IoU is not evaluated",
            "peak RSS is the process-lifetime OS high-water mark observed after attack and decode",
            "temporary disk peak is 0 because A4 attacks and decode run in memory; output/checkpoint storage is excluded",
        ],
    }


def test_row_validation_rejects_duplicate_missing_and_canonical_shape_tampering():
    plan = build_v2_pregate_plan(CORPUS, PROFILES, MATRIX, seed=20260827)
    row = _minimal_valid_row(plan)

    with pytest.raises(ValueError, match="duplicate"):
        _validate_rows([row, row], plan, require_complete=False)
    with pytest.raises(ValueError, match="missing"):
        _validate_rows([], plan, require_complete=True)
    with pytest.raises(ValueError, match="canonical_shape"):
        _validate_rows(
            [{**row, "canonical_shape": [1152, 2304]}],
            plan,
            require_complete=False,
        )


def test_row_validation_rejects_unexpected_private_field():
    plan = build_v2_pregate_plan(CORPUS, PROFILES, MATRIX, seed=20260827)

    with pytest.raises(ValueError, match="unexpected"):
        _validate_rows(
            [{**_minimal_valid_row(plan), "private_debug_trace": "do-not-export"}],
            plan,
            require_complete=False,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", True),
        ("algorithm_version", 2.0),
        ("attack_parameters", {"quality": 70.0}),
    ],
)
def test_row_validation_rejects_provenance_type_confusion(field, value):
    plan = build_v2_pregate_plan(CORPUS, PROFILES, MATRIX, seed=20260827)

    with pytest.raises(ValueError, match="provenance mismatch"):
        _validate_rows(
            [{**_minimal_valid_row(plan, attack_id="jpeg-q70"), field: value}],
            plan,
            require_complete=False,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("case_seed", 0),
        ("corpus_sha256", "0" * 64),
        ("outcome", "true_attribution"),
    ],
)
def test_row_validation_reconstructs_seed_source_and_outcome(field, value):
    plan = build_v2_pregate_plan(CORPUS, PROFILES, MATRIX, seed=20260827)

    with pytest.raises(ValueError):
        _validate_rows(
            [{**_minimal_valid_row(plan), field: value}],
            plan,
            require_complete=False,
        )


@pytest.mark.parametrize("valid_vote_count", [0, 1])
def test_decoded_positive_row_requires_two_independent_votes(valid_vote_count):
    plan = build_v2_pregate_plan(CORPUS, PROFILES, MATRIX, seed=20260827)
    row = _minimal_valid_row(plan)
    row.update(
        {
            "algorithm_status": "decoded",
            "reason": "decoded",
            "decoded_id": row["expected_id"],
            "outcome": "true_attribution",
            "valid_vote_count": valid_vote_count,
            "bit_error_rate": 0.0,
        }
    )

    with pytest.raises(ValueError, match="valid_vote_count"):
        _validate_rows([row], plan, require_complete=False)


def test_valid_vote_count_cannot_exceed_the_candidate_repetition_bound():
    plan = build_v2_pregate_plan(CORPUS, PROFILES, MATRIX, seed=20260827)
    row = _minimal_valid_row(plan)
    row.update(
        {
            "algorithm_status": "partial_payload_evidence",
            "reason": "partial",
            "outcome": "partial",
            "valid_vote_count": int(plan.candidates[0].values["payload_repetitions"]) + 1,
            "bit_error_rate": 0.0,
        }
    )

    with pytest.raises(ValueError, match="valid_vote_count"):
        _validate_rows([row], plan, require_complete=False)


@pytest.mark.parametrize(
    ("algorithm_status", "reason", "valid_vote_count", "bit_error_rate"),
    [
        ("partial_payload_evidence", "partial", 0, 0.0),
        ("payload_not_detected", "not_detected", 1, None),
        ("decoded", "decoded", 2, None),
    ],
)
def test_v2_evidence_status_requires_the_producer_vote_and_ber_shape(
    algorithm_status, reason, valid_vote_count, bit_error_rate
):
    plan = build_v2_pregate_plan(CORPUS, PROFILES, MATRIX, seed=20260827)
    row = _minimal_valid_row(plan)
    row.update(
        {
            "algorithm_status": algorithm_status,
            "reason": reason,
            "valid_vote_count": valid_vote_count,
            "bit_error_rate": bit_error_rate,
        }
    )
    if algorithm_status == "decoded":
        row.update(
            {
                "decoded_id": row["expected_id"],
                "outcome": "true_attribution",
            }
        )
    elif algorithm_status == "partial_payload_evidence":
        row["outcome"] = "partial"

    with pytest.raises(ValueError):
        _validate_rows([row], plan, require_complete=False)


def test_non_decoded_v2_evidence_cannot_expose_an_issuance_id():
    plan = build_v2_pregate_plan(CORPUS, PROFILES, MATRIX, seed=20260827)
    row = _minimal_valid_row(plan)
    row.update(
        {
            "algorithm_status": "partial_payload_evidence",
            "reason": "partial",
            "decoded_id": row["expected_id"],
            "outcome": "true_attribution",
            "valid_vote_count": 1,
            "bit_error_rate": 0.0,
        }
    )

    with pytest.raises(ValueError, match="non-decoded"):
        _validate_rows([row], plan, require_complete=False)


def _retained_pregate_row(fixture_id, attack_id):
    results = ROOT / "reports" / "fingerprint-pregate-v2" / "results.jsonl"
    for line in results.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["fixture_id"] == fixture_id and row["attack_id"] == attack_id:
            return row
    raise AssertionError(f"retained row not found: {fixture_id}/{attack_id}")


def test_row_validation_reconstructs_tamper_ground_truth_from_provenance():
    plan = build_v2_pregate_plan(CORPUS, PROFILES, MATRIX, seed=20260827)
    row = _retained_pregate_row("tamper-ground-truth", "crop-f0p25")
    tampered = deepcopy(row)
    tampered["tamper_ground_truth"][0]["x"] += 0.01

    with pytest.raises(ValueError, match="tamper_ground_truth"):
        _validate_rows([tampered], plan, require_complete=False)


def test_row_validation_reconstructs_removed_crop_fraction_from_provenance():
    plan = build_v2_pregate_plan(CORPUS, PROFILES, MATRIX, seed=20260827)
    row = _retained_pregate_row("tamper-ground-truth", "crop-f0p25")
    tampered = deepcopy(row)
    tampered["removed_area_fraction"] -= 0.01

    with pytest.raises(ValueError, match="removed_area_fraction"):
        _validate_rows([tampered], plan, require_complete=False)


@pytest.mark.parametrize("execution_error", [False, True])
def test_row_validation_rejects_arbitrary_trailing_limitations(execution_error):
    plan = build_v2_pregate_plan(CORPUS, PROFILES, MATRIX, seed=20260827)
    row = _minimal_valid_row(plan)
    if execution_error:
        row.update(
            {
                "reason": "execution_error",
                "algorithm_status": "execution_error",
                "outcome": "execution_error",
                "removed_area_fraction": None,
            }
        )
    row["limitations"].append("arbitrary trailing limitation")

    with pytest.raises(ValueError, match="limitations"):
        _validate_rows([row], plan, require_complete=False)


def test_execution_error_allows_one_structured_producer_diagnostic():
    plan = build_v2_pregate_plan(CORPUS, PROFILES, MATRIX, seed=20260827)
    row = _minimal_valid_row(plan)
    row.update(
        {
            "reason": "execution_error",
            "algorithm_status": "execution_error",
            "outcome": "execution_error",
            "removed_area_fraction": None,
        }
    )
    row["limitations"].append("embedding RuntimeError: synthetic diagnostic")

    _validate_rows([row], plan, require_complete=False)


def test_execution_error_allows_exact_no_artifact_evidence_after_attack_failure():
    plan = build_v2_pregate_plan(CORPUS, PROFILES, MATRIX, seed=20260827)
    row = _minimal_valid_row(plan)
    row.update(
        {
            "reason": "execution_error",
            "algorithm_status": "execution_error",
            "outcome": "execution_error",
            "removed_area_fraction": None,
        }
    )
    row["limitations"].append("RuntimeError: synthetic attack diagnostic")

    _validate_rows([row], plan, require_complete=False)


def test_eligible_crop_execution_error_cannot_be_removed_from_the_denominator():
    plan = build_v2_pregate_plan(CORPUS, PROFILES, MATRIX, seed=20260827)
    row = {
        **_minimal_valid_row(plan, attack_id="crop-f0p25"),
        "reason": "execution_error",
        "algorithm_status": "execution_error",
        "outcome": "execution_error",
        "eligible": True,
        "remaining_embedded_tiles": None,
        "eligibility_reason": "eligible",
        "removed_area_fraction": None,
        "limitations": [
            "A5 integrity localization is not implemented; tamper ground truth is recorded but localization IoU is not evaluated",
            "peak RSS is the process-lifetime OS high-water mark observed after attack and decode",
            "temporary disk peak is 0 because A4 attacks and decode run in memory; output/checkpoint storage is excluded",
            "embedding RuntimeError: synthetic diagnostic",
        ],
    }

    with pytest.raises(ValueError, match="crop eligibility"):
        _validate_rows([row], plan, require_complete=False)


def test_any_candidate_execution_error_empties_selection_despite_forged_global_zero():
    scores = list(_canonical_scores())
    scores[1] = replace(
        scores[1], execution_errors=1, failed_gates=("execution_errors_zero",)
    )
    forged = _summary(*scores, execution_errors=0, status="complete")

    assert select_qualified_candidates(forged, fingerprint_candidates_v2()) == ()


def test_loader_reconstructs_forged_global_zero_from_validated_rows(tmp_path, monkeypatch):
    plan = build_v2_pregate_plan(CORPUS, PROFILES, MATRIX, seed=20260827)
    results = b'{"reason":"execution_error"}\n'
    scores = list(_canonical_scores())
    scores[1] = replace(
        scores[1], execution_errors=1, failed_gates=("execution_errors_zero",)
    )
    preliminary = PreGateSummaryV2(
        status="complete",
        planned_rows=1408,
        completed_rows=1408,
        execution_errors=0,
        contract_hashes={
            "profiles_sha256": hashlib.sha256(PROFILES.read_bytes()).hexdigest(),
            "corpus_sha256": hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
            "attack_matrix_sha256": hashlib.sha256(MATRIX.read_bytes()).hexdigest(),
        },
        plan_sha256=plan.plan_sha256,
        results_sha256=hashlib.sha256(results).hexdigest(),
        qualified_candidate_ids=(),
        candidates=tuple(scores),
        limitations=(),
    )
    forged = replace(
        preliminary,
        qualified_candidate_ids=pregate_v2._qualified_ids(preliminary),
    )
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(
        json.dumps(pregate_v2._summary_document(forged), sort_keys=True),
        encoding="utf-8",
    )
    (tmp_path / "results.jsonl").write_bytes(results)
    monkeypatch.setattr(pregate_v2, "_validate_rows", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        pregate_v2, "_aggregate_scores", lambda *args, **kwargs: tuple(scores)
    )

    with pytest.raises(ValueError, match="tampered"):
        pregate_v2.load_v2_pregate_summary(summary_path, PROFILES)


def test_pregate_checkpoint_resume_identity_is_exact_and_bounded():
    plan = build_v2_pregate_plan(CORPUS, PROFILES, MATRIX, seed=20260827)
    different = build_v2_pregate_plan(CORPUS, PROFILES, MATRIX, seed=20260828)
    connection = sqlite3.connect(":memory:")
    try:
        _initialize_checkpoint(connection, _run_identity(plan, 0, 1))
        with pytest.raises(ValueError, match="different benchmark run"):
            _initialize_checkpoint(connection, _run_identity(different, 0, 1))
    finally:
        connection.close()


def _bounded_v2_contracts(tmp_path):
    source = np.zeros((24, 32, 3), dtype=np.uint8)
    image_path = tmp_path / "source.png"
    assert cv2.imwrite(str(image_path), source)
    corpus = tmp_path / "corpus.json"
    corpus.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entries": [
                    {
                        "fixture_id": "trusted-canvas",
                        "kind": "clean_image",
                        "relative_path": image_path.name,
                        "pages": 1,
                        "sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    matrix = tmp_path / "matrix.json"
    matrix.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "jpeg_quality": [],
                "crop_fraction": [],
                "resize_scale": [0.75],
                "rotation_degrees": [],
                "brightness_contrast": [],
                "gaussian_noise_blur": [],
                "screenshot": [],
                "combined": [],
                "tamper": [],
            }
        ),
        encoding="utf-8",
    )
    return corpus, matrix


@pytest.mark.parametrize("runtime_failure", [False, True])
def test_v2_runner_uses_only_the_pre_attack_canvas_and_classifies_runtime_failures(
    tmp_path, monkeypatch, runtime_failure
):
    corpus, matrix = _bounded_v2_contracts(tmp_path)
    observed = {}

    monkeypatch.setattr(
        runner,
        "embed_fingerprint_v2",
        lambda page, context, profile: SimpleNamespace(image=page.copy()),
    )

    def decode(attacked, key, page_index, canonical_shape, profiles):
        observed["attacked_shape"] = attacked.shape[:2]
        observed["canonical_shape"] = canonical_shape
        if runtime_failure:
            raise AlignmentV2RuntimeError("pilot_estimation", 0)
        return DecodeV2Decision(
            None, 0.0, 0, None, "insufficient_sync_evidence"
        )

    monkeypatch.setattr(runner, "decode_fingerprint_v2", decode)
    output = tmp_path / ("runtime" if runtime_failure else "missing-evidence")
    plan = runner.build_execution_plan(
        corpus,
        PROFILES,
        matrix,
        seed=20260827,
    )
    summary = runner._run_execution_plan(
        plan,
        output,
        max_rows=1,
    )
    row = json.loads((output / "results.jsonl").read_text(encoding="utf-8"))

    assert observed == {
        "attacked_shape": (1152, 2304),
        "canonical_shape": (1536, 3072),
    }
    assert row["canonical_shape"] == [1536, 3072]
    assert row["reason"] == ("execution_error" if runtime_failure else "not_detected")
    assert row["algorithm_status"] == (
        "execution_error" if runtime_failure else "insufficient_sync_evidence"
    )
    assert summary.failed_rows == (1 if runtime_failure else 0)
