import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from splitbind_bench import pregate_v3, runner
from splitbind_bench.pregate_v3 import (
    PreGateCandidateScoreV3,
    PreGateSummaryV3,
    _decode_json_object,
    _validate_rows,
    build_v3_pregate_plan,
    load_qualified_candidate_selection_v3,
    load_v3_pregate_summary,
    select_qualified_candidates_v3,
)
from splitbind_bench.runner import CorpusSource, _case_context, _case_seed, _row_identifier
from splitbind_ref.contracts import fingerprint_candidates_v3
from splitbind_ref.fingerprint_v3 import DecodeV3Decision
from splitbind_ref.fingerprint_v3_profile import candidate_identifier_v3, load_v3_profiles


ROOT = Path(__file__).resolve().parents[4]
PROFILES = ROOT / "contracts" / "algorithm" / "fingerprint-candidates.v3.json"
CORPUS = ROOT / "fixtures" / "corpus" / "corpus-manifest.v1.json"
MATRIX = ROOT / "contracts" / "algorithm" / "attack-matrix.v1.json"


def _score_for(profile, **overrides) -> PreGateCandidateScoreV3:
    values = {
        "profile_id": hashlib.sha256(candidate_identifier_v3(profile)).hexdigest(),
        "candidate_id": candidate_identifier_v3(profile).hex(),
        "scheduled_rows": 88,
        "execution_errors": 0,
        "false_attributions": 0,
        "jpeg70_true_attributions": 12,
        "jpeg70_denominator": 12,
        "jpeg70_decode_rate": 1.0,
        "resize075_true_attributions": 12,
        "resize075_denominator": 12,
        "resize075_decode_rate": 1.0,
        "crop025_true_attributions": 12,
        "crop025_denominator": 12,
        "crop025_decode_rate": 1.0,
        "quality_observations": 12,
        "minimum_psnr_db": 38.0,
        "minimum_ssim": 0.95,
        "failed_gates": (),
    }
    values.update(overrides)
    return PreGateCandidateScoreV3(**values)


def _canonical_scores(**first_overrides) -> tuple[PreGateCandidateScoreV3, ...]:
    return tuple(
        _score_for(profile, **(first_overrides if index == 0 else {}))
        for index, profile in enumerate(load_v3_profiles())
    )


def _summary(
    scores: tuple[PreGateCandidateScoreV3, ...] | None = None, **overrides
) -> PreGateSummaryV3:
    candidate_scores = scores or _canonical_scores()
    values = {
        "status": "complete",
        "planned_rows": 352,
        "completed_rows": 352,
        "execution_errors": 0,
        "false_attributions": 0,
        "contract_hashes": {
            "profiles_sha256": hashlib.sha256(PROFILES.read_bytes()).hexdigest(),
            "corpus_sha256": hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
            "attack_matrix_sha256": hashlib.sha256(MATRIX.read_bytes()).hexdigest(),
        },
        "plan_sha256": "1" * 64,
        "results_sha256": "2" * 64,
        "results_csv_sha256": "3" * 64,
        "qualified_candidate_ids": tuple(
            sorted(score.candidate_id for score in candidate_scores if not score.failed_gates)
        ),
        "candidates": candidate_scores,
        "limitations": (),
    }
    values.update(overrides)
    return PreGateSummaryV3(**values)


def test_v3_pregate_plan_is_complete_and_bounded():
    plan = build_v3_pregate_plan(CORPUS, PROFILES, MATRIX, seed=20260905)

    assert plan.algorithm_version == 3
    assert plan.candidate_count <= 16
    assert plan.candidate_count == 4
    assert [case.case_id for case in plan.attacks] == [
        "identity",
        "jpeg-q70",
        "resize-s0p75",
        "crop-f0p25",
    ]
    assert plan.planned_rows == plan.corpus_pages * plan.candidate_count * plan.attack_count
    assert plan.planned_rows == 352


@pytest.mark.parametrize(
    ("field", "value", "failed_gate"),
    [
        ("jpeg70_decode_rate", 0.94, "jpeg70_decode_rate_at_least_0.95"),
        ("resize075_decode_rate", 0.94, "resize075_decode_rate_at_least_0.95"),
        ("crop025_decode_rate", 0.89, "crop025_decode_rate_at_least_0.90"),
        ("false_attributions", 1, "false_attributions_zero"),
        ("execution_errors", 1, "execution_errors_zero"),
        ("minimum_psnr_db", 37.99, "minimum_psnr_db_at_least_38"),
        ("minimum_ssim", 0.949, "minimum_ssim_at_least_0.95"),
    ],
)
def test_v3_selection_stays_empty_when_any_required_gate_fails(
    field, value, failed_gate
):
    scores = _canonical_scores(**{field: value, "failed_gates": (failed_gate,)})

    assert (
        select_qualified_candidates_v3(_summary(scores), fingerprint_candidates_v3())
        == ()
    )


@pytest.mark.parametrize(
    "summary",
    [
        _summary(execution_errors=1, status="complete_with_errors"),
        _summary(false_attributions=1),
        _summary(completed_rows=351, status="incomplete"),
    ],
)
def test_global_error_false_attribution_or_incomplete_population_fails_closed(summary):
    assert select_qualified_candidates_v3(summary, fingerprint_candidates_v3()) == ()


def test_selection_rejects_contract_hash_tampering():
    hashes = dict(_summary().contract_hashes)
    hashes["profiles_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="contract"):
        select_qualified_candidates_v3(
            _summary(contract_hashes=hashes), fingerprint_candidates_v3()
        )


def test_selection_rejects_wrong_candidate_population_and_qualified_id():
    missing = _canonical_scores()[:-1]
    with pytest.raises(ValueError, match="candidate"):
        select_qualified_candidates_v3(_summary(missing), fingerprint_candidates_v3())

    complete = _canonical_scores()
    with pytest.raises(ValueError, match="qualified"):
        select_qualified_candidates_v3(
            _summary(complete, qualified_candidate_ids=("00",)),
            fingerprint_candidates_v3(),
        )


def test_json_decoder_rejects_duplicate_schema_and_nan():
    with pytest.raises(ValueError, match="duplicate"):
        _decode_json_object(b'{"schema_version":3,"schema_version":3}', "summary")
    with pytest.raises(ValueError, match="finite"):
        _decode_json_object(b'{"minimum_ssim":NaN}', "summary")


def test_v3_summary_schema_binds_final_csv_hash():
    document = pregate_v3._summary_document(_summary())

    assert "results_csv_sha256" in document


def test_v3_summary_loader_fails_closed_when_csv_bytes_are_tampered(tmp_path, monkeypatch):
    plan = build_v3_pregate_plan(CORPUS, PROFILES, MATRIX, seed=20260905)
    results = b"{}\n"
    clean_csv = b"row_id\nclean\n"
    tampered_csv = b"row_id\ntampered\n"
    document = {
        "schema_version": 3,
        "status": "incomplete",
        "evidence_scope": "research_measurement_only",
        "profile_promoted": False,
        "planned_rows": 352,
        "completed_rows": 1,
        "execution_errors": 0,
        "false_attributions": 0,
        "contract_hashes": _summary().contract_hashes,
        "plan_sha256": plan.plan_sha256,
        "results_sha256": hashlib.sha256(results).hexdigest(),
        "results_csv_sha256": hashlib.sha256(clean_csv).hexdigest(),
        "qualified_candidate_ids": [],
        "candidates": [asdict(score) for score in _canonical_scores()],
        "limitations": [],
    }
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
    (tmp_path / "results.jsonl").write_bytes(results)
    (tmp_path / "results.csv").write_bytes(tampered_csv)
    monkeypatch.setattr(pregate_v3, "_validate_rows", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        pregate_v3, "_aggregate_scores", lambda *args, **kwargs: _canonical_scores()
    )

    with pytest.raises(ValueError, match="CSV hash"):
        load_v3_pregate_summary(summary_path, PROFILES)


def test_v3_selection_loader_fails_closed_when_csv_hash_is_tampered(tmp_path):
    summary = b"{}"
    results = b"{}\n"
    csv_bytes = b"row_id\n"
    selection_path = tmp_path / "qualified-candidate-ids.json"
    selection_path.write_text(
        json.dumps(
            {
                "schema_version": 3,
                "source_contract_sha256": hashlib.sha256(PROFILES.read_bytes()).hexdigest(),
                "pregate_plan_sha256": "1" * 64,
                "pregate_results_sha256": hashlib.sha256(results).hexdigest(),
                "pregate_results_csv_sha256": "0" * 64,
                "pregate_summary_sha256": hashlib.sha256(summary).hexdigest(),
                "qualified_candidate_ids": [],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "summary.json").write_bytes(summary)
    (tmp_path / "results.jsonl").write_bytes(results)
    (tmp_path / "results.csv").write_bytes(csv_bytes)

    with pytest.raises(ValueError, match="CSV hash"):
        load_qualified_candidate_selection_v3(selection_path, PROFILES)


@pytest.mark.parametrize("suffix", [".png", ".pdf"])
def test_v3_source_preflight_rejects_oversized_metadata_before_rasterization(
    tmp_path, monkeypatch, suffix
):
    source_path = tmp_path / f"oversized{suffix}"
    source_path.write_bytes(b"fixture")
    source = CorpusSource(
        "oversized",
        "clean_image",
        source_path,
        hashlib.sha256(source_path.read_bytes()).hexdigest(),
        1,
        (),
    )
    decoded = False

    if suffix == ".png":
        monkeypatch.setattr(runner, "_image_dimensions", lambda path: (10_000, 4_001))

        def decode(*args, **kwargs):
            nonlocal decoded
            decoded = True
            raise AssertionError("image decode must not run")

        monkeypatch.setattr(runner.cv2, "imread", decode)
    else:
        class Document:
            def __len__(self):
                return 1

            def get_page_size(self, page_index):
                return (5_000, 4_001)

            def __getitem__(self, page_index):
                nonlocal decoded
                decoded = True
                raise AssertionError("PDF render page must not be opened")

            def close(self):
                return None

        monkeypatch.setattr(runner.pdfium, "PdfDocument", lambda path: Document())

    with pytest.raises(ValueError, match="pixel limit"):
        list(runner._iter_sources((source,), max_source_pixels=40_000_000))

    assert decoded is False


def test_legacy_source_iteration_does_not_enable_v3_metadata_preflight(tmp_path, monkeypatch):
    source_path = tmp_path / "legacy.png"
    source_path.write_bytes(b"fixture")
    source = CorpusSource(
        "legacy",
        "clean_image",
        source_path,
        hashlib.sha256(source_path.read_bytes()).hexdigest(),
        1,
        (),
    )
    monkeypatch.setattr(
        runner,
        "_image_dimensions",
        lambda path: (_ for _ in ()).throw(AssertionError("legacy preflight invoked")),
    )
    monkeypatch.setattr(
        runner.cv2,
        "imread",
        lambda *args, **kwargs: runner.np.zeros((1, 1, 3), dtype="uint8"),
    )

    assert len(list(runner._iter_sources((source,)))) == 1


def _minimal_valid_row(plan, *, attack_id="identity"):
    source = plan.sources[0]
    candidate = plan.candidates[0]
    attack = next(case for case in plan.attacks if case.case_id == attack_id)
    expected = str(
        _case_context(plan.seed, source.fixture_id, 0, candidate.profile_sha256)[0]
    )
    return {
        "schema_version": 1,
        "algorithm_version": 3,
        "row_id": _row_identifier(source.fixture_id, 0, candidate.profile_sha256, attack.case_id),
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


def test_row_validation_rejects_missing_excess_and_wrong_decoded_id():
    plan = build_v3_pregate_plan(CORPUS, PROFILES, MATRIX, seed=20260905)
    row = _minimal_valid_row(plan)

    with pytest.raises(ValueError, match="missing"):
        _validate_rows([], plan, require_complete=True)
    with pytest.raises(ValueError, match="duplicate"):
        _validate_rows([row, row], plan, require_complete=False)

    wrong_id = str(_case_context(plan.seed + 1, row["fixture_id"], 0, row["algorithm_profile_sha256"])[0])
    forged = {
        **row,
        "algorithm_status": "decoded",
        "reason": "decoded",
        "decoded_id": wrong_id,
        "outcome": "false_attribution",
        "valid_vote_count": 2,
        "bit_error_rate": 0.0,
    }
    _validate_rows([forged], plan, require_complete=False)


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        ("conflicting_payload_evidence", "not_detected"),
        ("partial_payload_evidence", "partial"),
        ("payload_not_detected", "not_detected"),
        ("insufficient_sync_evidence", "not_detected"),
        ("geometry_rejected", "not_detected"),
    ],
)
def test_non_decoded_v3_statuses_never_expose_an_identity(status, reason):
    plan = build_v3_pregate_plan(CORPUS, PROFILES, MATRIX, seed=20260905)
    row = _minimal_valid_row(plan)
    row.update(
        {
            "algorithm_status": status,
            "reason": reason,
            "decoded_id": row["expected_id"],
            "outcome": "true_attribution",
            "valid_vote_count": 1 if status == "partial_payload_evidence" else 0,
            "bit_error_rate": 0.0 if status == "partial_payload_evidence" else None,
        }
    )

    with pytest.raises(ValueError, match="non-decoded"):
        _validate_rows([row], plan, require_complete=False)


def test_conflicting_v3_evidence_preserves_votes_and_ber_without_exposing_identity():
    plan = build_v3_pregate_plan(CORPUS, PROFILES, MATRIX, seed=20260905)
    row = _minimal_valid_row(plan)
    row.update(
        {
            "algorithm_status": "conflicting_payload_evidence",
            "valid_vote_count": 1,
            "bit_error_rate": 0.0,
        }
    )

    _validate_rows([row], plan, require_complete=False)


def test_runner_passes_positive_sync_template_and_no_negative_template(tmp_path, monkeypatch):
    plan = build_v3_pregate_plan(CORPUS, PROFILES, MATRIX, seed=20260905, smoke=True)
    observed = []
    sync_template = object()

    def embed(page, context, profile):
        return SimpleNamespace(image=page.copy(), sync_template=sync_template)

    def decode(image, key, page_index, canonical_shape, profiles, orb_template=None):
        observed.append(orb_template)
        return DecodeV3Decision(None, 0.0, 0, None, "payload_not_detected")

    monkeypatch.setattr(runner, "embed_fingerprint_v3", embed)
    monkeypatch.setattr(runner, "decode_fingerprint_v3", decode)
    reduced = replace(plan, attacks=(plan.attacks[0],), attack_count=1, planned_rows=2)

    summary = runner._run_execution_plan(reduced, tmp_path / "runner-v3")

    assert summary.completed_rows == 2
    assert observed == [sync_template, None]
    rows = [
        json.loads(line)
        for line in (tmp_path / "runner-v3" / "results.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
    ]
    assert {row["algorithm_version"] for row in rows} == {3}
    assert {row["candidate_id"] for row in rows} == {
        candidate_identifier_v3(load_v3_profiles()[0]).hex()
    }
