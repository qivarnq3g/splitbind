import hashlib
import json
import sqlite3
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
from splitbind_bench.runner import _case_context, _initialize_checkpoint, _row_identifier, _run_identity
from splitbind_ref.fingerprint_v2 import DecodeV2Decision
from splitbind_ref.contracts import fingerprint_candidates_v2
from splitbind_ref.fingerprint_v2_profile import candidate_identifier_v2, load_v2_profiles
from splitbind_ref.synchronization_v2 import AlignmentV2RuntimeError


ROOT = Path(__file__).resolve().parents[4]
PROFILES = ROOT / "contracts" / "algorithm" / "fingerprint-candidates.v2.json"
CORPUS = ROOT / "fixtures" / "corpus" / "corpus-manifest.v1.json"
MATRIX = ROOT / "contracts" / "algorithm" / "attack-matrix.v1.json"


def _score(**overrides) -> PreGateCandidateScoreV2:
    profile = load_v2_profiles()[0]
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
        _summary(_score(), execution_errors=1, status="complete_with_errors"),
        _summary(_score(), completed_rows=1407, status="incomplete"),
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
    failed = _score(**{field: value}, failed_gates=(failed_gate,))

    assert select_qualified_candidates(_summary(failed), fingerprint_candidates_v2()) == ()


def test_selection_is_sorted_by_binary_candidate_identifier():
    profiles = load_v2_profiles()
    second = _score(
        profile_id=hashlib.sha256(candidate_identifier_v2(profiles[1])).hexdigest(),
        candidate_id=candidate_identifier_v2(profiles[1]).hex(),
    )
    first = _score()
    summary = _summary(second, first)

    selected = select_qualified_candidates(summary, fingerprint_candidates_v2())

    assert selected == tuple(sorted((bytes.fromhex(first.candidate_id), bytes.fromhex(second.candidate_id))))


def test_selection_rejects_a_source_contract_hash_mismatch():
    summary = _summary(
        _score(),
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
    failed = replace(_score(), mean_ssim=0.94, failed_gates=("mean_ssim_at_least_0.95",))
    tampered = _summary(failed, qualified_candidate_ids=(failed.candidate_id,))

    with pytest.raises(ValueError, match="qualified"):
        select_qualified_candidates(tampered, fingerprint_candidates_v2())


def _minimal_valid_row(plan):
    source = plan.sources[0]
    candidate = plan.candidates[0]
    attack = plan.attacks[0]
    expected = str(
        _case_context(plan.seed, source.fixture_id, 0, candidate.profile_sha256)[0]
    )
    return {
        "schema_version": 1,
        "algorithm_version": 2,
        "row_id": _row_identifier(
            source.fixture_id, 0, candidate.profile_sha256, attack.case_id
        ),
        "corpus_contract_sha256": plan.corpus_contract_sha256,
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
        "seed": plan.seed,
        "canonical_shape": [1536, 3072],
        "expected_id": expected,
        "decoded_id": None,
        "reason": "not_detected",
        "algorithm_status": "insufficient_sync_evidence",
        "eligible": True,
        "remaining_embedded_tiles": None,
        "eligibility_reason": "eligible",
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
    summary = runner.run_matrix(
        corpus,
        PROFILES,
        matrix,
        seed=20260827,
        output_dir=output,
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
