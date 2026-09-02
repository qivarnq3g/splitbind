"""Trust-boundary tests for the V2 promotion/no-release decision."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from splitbind_bench.promotion_v2 import (
    BenchmarkSummaryV2,
    NoEligibleProfileV2,
    ProfileScore,
    V2PromotionInputs,
    ensure_v2_release_absent,
    eligible_v2_profiles,
    promote_v2_after_report,
    promote_profile_v2,
    verify_v2_pinned_inputs,
)
from splitbind_bench import promotion_v2
from splitbind_bench.runner import build_execution_plan


ROOT = Path(__file__).resolve().parents[4]
PROFILES = ROOT / "contracts" / "algorithm" / "fingerprint-candidates.v2.json"
CORPUS = ROOT / "fixtures" / "corpus" / "corpus-manifest.v1.json"
MATRIX = ROOT / "contracts" / "algorithm" / "attack-matrix.v1.json"
SELECTION = ROOT / "reports" / "fingerprint-pregate-v2" / "qualified-candidate-ids.json"
PROMOTE_SCRIPT = ROOT / "research" / "python" / "scripts" / "promote_profile_v2.py"


def _candidate() -> tuple[str, str]:
    plan = build_execution_plan(CORPUS, PROFILES, MATRIX, 20260827)
    candidate = plan.candidates[0]
    assert candidate.candidate_id is not None
    return candidate.profile_sha256, candidate.candidate_id


def _score(
    *,
    jpeg70: float = 0.95,
    resize075: float = 0.95,
    crop025: float = 0.90,
    psnr: float = 38.0,
    ssim: float = 0.95,
    false_attribution: int = 0,
    execution_errors: int = 0,
    milliseconds: float = 10.0,
) -> ProfileScore:
    profile_id, candidate_id = _candidate()
    return ProfileScore(
        profile_id=profile_id,
        candidate_id=candidate_id,
        false_attribution=false_attribution,
        execution_errors=execution_errors,
        scheduled_rows=682,
        jpeg70_true_attribution=round(12 * jpeg70),
        jpeg70_denominator=12,
        jpeg70_rate=jpeg70,
        resize075_true_attribution=round(12 * resize075),
        resize075_denominator=12,
        resize075_rate=resize075,
        crop025_true_attribution=round(10 * crop025),
        crop025_denominator=10,
        crop025_rate=crop025,
        quality_observations=12,
        mean_psnr_db=psnr,
        mean_ssim=ssim,
        processing_observations=682,
        processing_ms_per_page=milliseconds,
        failed_gates=(),
    )


def _summary(*scores: ProfileScore, execution_errors: int = 0) -> BenchmarkSummaryV2:
    return BenchmarkSummaryV2(
        schema_version=2,
        status="complete",
        seed=20260827,
        corpus_pages=22,
        candidate_count=len(scores),
        attack_count=31,
        planned_rows=682 * len(scores),
        completed_rows=682 * len(scores),
        execution_errors=execution_errors,
        contract_hashes={},
        plan_sha256="0" * 64,
        results_sha256="1" * 64,
        source_summary_sha256="2" * 64,
        candidate_selection_sha256="3" * 64,
        profiles=tuple(scores),
        limitations=("synthetic unit-test evidence",),
        execution_error_details=(),
    )


def test_v2_release_requires_every_unchanged_gate():
    passing = _summary(_score())

    assert len(eligible_v2_profiles(passing)) == 1
    for field, failing_value in {
        "jpeg70": 0.949,
        "resize075": 0.949,
        "crop025": 0.899,
        "psnr": 37.999,
        "ssim": 0.949,
        "false_attribution": 1,
        "execution_errors": 1,
    }.items():
        assert eligible_v2_profiles(_summary(_score(**{field: failing_value}))) == ()


def test_v2_eligible_profiles_rank_deterministically_by_quality_then_speed():
    first = _score(ssim=0.96, milliseconds=9.0)
    second = replace(first, mean_ssim=0.97, processing_ms_per_page=100.0)

    ranked = eligible_v2_profiles(_summary(first, second))

    assert [score.mean_ssim for score in ranked] == [0.97, 0.96]


def test_v2_eligible_profiles_use_profile_hash_as_the_final_tie_break():
    base = _score()
    later = replace(base, profile_id="b", candidate_id="candidate-b")
    earlier = replace(base, profile_id="a", candidate_id="candidate-a")

    assert [score.profile_id for score in eligible_v2_profiles(_summary(later, earlier))] == ["a", "b"]


def test_promote_v2_writes_the_best_synthetic_passing_candidate(tmp_path):
    summary = _summary(_score())
    output = tmp_path / "fingerprint-profile.v2.json"

    released = promote_profile_v2(summary, output)

    assert output.is_file()
    assert released.destination == output.absolute()
    document = json.loads(output.read_text(encoding="utf-8"))
    assert document["schema_version"] == 2
    assert document["candidate_provenance"]["algorithm_profile_sha256"] == released.profile_id


def test_promote_v2_removes_only_exact_stale_destination_when_no_profile_qualifies(tmp_path):
    output = tmp_path / "fingerprint-profile.v2.json"
    output.write_text("stale", encoding="utf-8")

    with pytest.raises(NoEligibleProfileV2):
        promote_profile_v2(_summary(_score(jpeg70=0.0)), output)

    assert not output.exists()


def test_v2_report_is_finalized_before_a_staged_release_is_published(tmp_path, monkeypatch):
    summary = _summary(_score())
    output = tmp_path / "fingerprint-profile.v2.json"
    report = tmp_path / "fingerprint-profile-v2.md"
    observed = []
    original = promotion_v2.write_v2_evaluation_report

    def checked_report(evidence, destination, released):
        observed.append((output.exists(), released.destination))
        original(evidence, destination, released)

    monkeypatch.setattr(promotion_v2, "write_v2_evaluation_report", checked_report)

    released = promote_v2_after_report(summary, output, report)

    assert observed == [(False, output.absolute())]
    assert output.is_file()
    assert "**Outcome:** Released." in report.read_text(encoding="utf-8")
    assert released.destination == output.absolute()


def test_ensure_v2_release_absent_unlinks_a_symlink_without_touching_its_target(tmp_path):
    target = tmp_path / "preserved.json"
    target.write_text("preserve", encoding="utf-8")
    output = tmp_path / "fingerprint-profile.v2.json"
    try:
        output.symlink_to(target)
    except OSError as error:
        pytest.skip(f"symlinks unavailable: {error}")

    ensure_v2_release_absent(output)

    assert not output.exists()
    assert target.read_text(encoding="utf-8") == "preserve"


@pytest.mark.parametrize("name", ["profiles", "corpus", "matrix", "selection"])
def test_v2_pinned_inputs_reject_substituted_contract_or_selection_bytes(tmp_path, name):
    profiles = tmp_path / PROFILES.name
    corpus = tmp_path / CORPUS.name
    matrix = tmp_path / MATRIX.name
    selection = tmp_path / SELECTION.name
    for source, destination in (
        (PROFILES, profiles),
        (CORPUS, corpus),
        (MATRIX, matrix),
        (SELECTION, selection),
    ):
        shutil.copyfile(source, destination)
    changed = {"profiles": profiles, "corpus": corpus, "matrix": matrix, "selection": selection}[name]
    if name == "selection":
        injected = json.loads(changed.read_text(encoding="utf-8"))
        injected["qualified_candidate_ids"] = [_candidate()[1]]
        changed.write_text(json.dumps(injected, sort_keys=True), encoding="utf-8")
    else:
        changed.write_bytes(changed.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="pinned|hash"):
        verify_v2_pinned_inputs(profiles, corpus, matrix, selection)


def test_v2_full_plan_hash_cannot_be_substituted_after_selection_validation(monkeypatch):
    full = build_execution_plan(CORPUS, PROFILES, MATRIX, 20260827)
    candidate = full.candidates[0]
    assert candidate.candidate_id is not None
    plan = replace(
        full,
        candidates=(candidate,),
        candidate_count=1,
        planned_rows=22 * 1 * 31,
        candidate_selection_sha256="4" * 64,
        plan_sha256="5" * 64,
    )
    inputs = V2PromotionInputs(
        profiles=PROFILES,
        corpus=CORPUS,
        matrix=MATRIX,
        selection=SELECTION,
        selection_sha256="4" * 64,
        selection_ids=(candidate.candidate_id,),
        selection_document={},
    )
    monkeypatch.setattr(promotion_v2, "REQUIRED_FULL_PLAN_SHA256", plan.plan_sha256)

    promotion_v2._validate_full_plan(plan, inputs)
    with pytest.raises(ValueError, match="plan hash"):
        promotion_v2._validate_full_plan(replace(plan, plan_sha256="6" * 64), inputs)


def test_no_release_cli_records_factual_empty_selection_and_removes_stale_output(tmp_path):
    output = tmp_path / "fingerprint-profile.v2.json"
    output.write_text("stale", encoding="utf-8")
    report = tmp_path / "fingerprint-profile-v2.md"

    completed = subprocess.run(
        [
            sys.executable,
            str(PROMOTE_SCRIPT),
            "--profiles", str(PROFILES),
            "--selection", str(SELECTION),
            "--output", str(output),
            "--report", str(report),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert not output.exists()
    assert "No release" in report.read_text(encoding="utf-8")


def _small_plan(*, attack_id: str = "jpeg-q95"):
    full = build_execution_plan(CORPUS, PROFILES, MATRIX, 20260827)
    source = next(source for source in full.sources if source.kind != "negative_external" and source.pages == 1)
    candidate = full.candidates[0]
    attack = next(attack for attack in full.attacks if attack.case_id == attack_id)
    return replace(full, sources=(source,), candidates=(candidate,), attacks=(attack,), planned_rows=1)


def _row_for(plan, *, attack_id: str | None = None):
    source, candidate = plan.sources[0], plan.candidates[0]
    attack = next(attack for attack in plan.attacks if attack.case_id == (attack_id or plan.attacks[0].case_id))
    expected = str(promotion_v2._case_context(20260827, source.fixture_id, 0, candidate.profile_sha256)[0])
    return {
        "schema_version": 1,
        "algorithm_version": 2,
        "row_id": promotion_v2._row_identifier(source.fixture_id, 0, candidate.profile_sha256, attack.case_id),
        "corpus_contract_sha256": plan.corpus_contract_sha256,
        "profile_contract_sha256": plan.profile_contract_sha256,
        "attack_matrix_sha256": plan.attack_matrix_sha256,
        "benchmark_plan_sha256": plan.plan_sha256,
        "seed": 20260827,
        "fixture_kind": source.kind,
        "fixture_id": source.fixture_id,
        "page_index": 0,
        "attack_id": attack.case_id,
        "attack_kind": attack.kind,
        "attack_parameters": dict(attack.parameters),
        "algorithm_profile_sha256": candidate.profile_sha256,
        "candidate_id": candidate.candidate_id,
        "expected_id": expected,
        "decoded_id": None,
        "reason": "not_detected",
        "algorithm_status": "payload_not_detected",
        "eligible": True,
        "eligibility_reason": "eligible",
        "remaining_embedded_tiles": None,
    }


def test_v2_row_validator_rejects_duplicate_or_missing_scheduled_rows():
    plan = _small_plan()
    row = _row_for(plan)

    with pytest.raises(ValueError, match="duplicate"):
        promotion_v2._validate_rows([row, row], replace(plan, planned_rows=2))
    with pytest.raises(ValueError, match="missing or surplus"):
        promotion_v2._validate_rows([], plan)


def test_v2_row_validator_reconstructs_crop_eligibility_instead_of_trusting_a_row():
    plan = _small_plan(attack_id="crop-f0p25")
    row = _row_for(plan)
    row.update(
        {
            "eligible": False,
            "eligibility_reason": "fewer_than_two_complete_embedded_tiles_remain",
            "remaining_embedded_tiles": 0,
        }
    )

    with pytest.raises(ValueError, match="eligibility"):
        promotion_v2._validate_rows([row], plan)


def test_execution_error_cannot_be_inflated_into_a_true_attribution():
    expected = "00000000-0000-4000-8000-000000000000"
    rows = [{"reason": "execution_error", "expected_id": expected, "decoded_id": expected}]

    assert promotion_v2._decode_counts(rows) == (0, 1)


def test_strict_v2_json_rejects_duplicate_keys_before_any_summary_field_is_trusted():
    with pytest.raises(ValueError, match="duplicate JSON object key"):
        promotion_v2._decode_json_object(b'{"status":"complete","status":"partial"}', "summary")


def test_no_release_cli_removes_stale_output_when_report_finalization_fails(tmp_path):
    output = tmp_path / "fingerprint-profile.v2.json"
    output.write_text("stale", encoding="utf-8")
    report = tmp_path / "report-directory"
    report.mkdir()

    completed = subprocess.run(
        [
            sys.executable,
            str(PROMOTE_SCRIPT),
            "--profiles", str(PROFILES),
            "--selection", str(SELECTION),
            "--output", str(output),
            "--report", str(report),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert not output.exists()
