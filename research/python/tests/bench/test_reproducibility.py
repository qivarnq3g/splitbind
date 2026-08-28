import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import cv2
import numpy as np
import pytest

from splitbind_bench.runner import (
    NONDETERMINISTIC_ROW_FIELDS,
    build_execution_plan,
    iter_corpus_pages,
    run_matrix,
)


ROOT = Path(__file__).resolve().parents[4]
PROFILES = ROOT / "contracts" / "algorithm" / "fingerprint-candidates.v1.json"
CORPUS = ROOT / "fixtures" / "corpus" / "corpus-manifest.v1.json"
MATRIX = ROOT / "contracts" / "algorithm" / "attack-matrix.v1.json"
SCRIPT = ROOT / "research" / "python" / "scripts" / "run_benchmark.py"


def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


@pytest.fixture
def bounded_contracts(tmp_path):
    source = np.empty((768, 1024, 3), dtype=np.uint8)
    y, x = np.indices(source.shape[:2], dtype=np.uint16)
    source[..., 0] = (x + 3 * y) % 256
    source[..., 1] = (5 * x + y) % 256
    source[..., 2] = (2 * x + 7 * y) % 256
    image_path = tmp_path / "source.png"
    assert cv2.imwrite(str(image_path), source)
    digest = hashlib.sha256(image_path.read_bytes()).hexdigest()
    corpus = tmp_path / "corpus.json"
    profiles = tmp_path / "profiles.json"
    matrix = tmp_path / "matrix.json"
    _write_json(
        corpus,
        {
            "schema_version": 1,
            "entries": [
                {
                    "fixture_id": "bounded-clean",
                    "kind": "clean_image",
                    "relative_path": image_path.name,
                    "pages": 1,
                    "sha256": digest,
                }
            ],
        },
    )
    _write_json(
        profiles,
        {
            "schema_version": 1,
            "fixed": json.loads(PROFILES.read_text(encoding="utf-8"))["fixed"],
            "sweep": {
                "qim_delta": [12.0],
                "tile_size_px": [256],
                "tiles_per_page": [12],
                "payload_repetitions": [3],
            },
        },
    )
    _write_json(
        matrix,
        {
            "schema_version": 1,
            "jpeg_quality": [95, 70],
            "crop_fraction": [],
            "resize_scale": [],
            "rotation_degrees": [],
            "brightness_contrast": [],
            "gaussian_noise_blur": [],
            "screenshot": [],
            "combined": [],
            "tamper": [],
        },
    )
    return corpus, profiles, matrix


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _normalized(rows):
    return [
        {key: value for key, value in row.items() if key not in NONDETERMINISTIC_ROW_FIELDS}
        for row in rows
    ]


def test_full_plan_is_the_complete_corpus_candidate_attack_cross_product():
    plan = build_execution_plan(CORPUS, PROFILES, MATRIX, seed=20260827)

    assert plan.corpus_pages == 22
    assert plan.candidate_count == 48
    assert plan.attack_count == 31
    assert plan.planned_rows == 22 * 48 * 31
    assert {case.kind for case in plan.attacks} == {
        "jpeg",
        "crop",
        "resize",
        "rotation",
        "brightness_contrast",
        "noise_blur",
        "screenshot",
        "combined",
        "tamper",
    }
    combined = [case for case in plan.attacks if case.kind == "combined"]
    assert [operation.kind for operation in combined[0].operations] == ["jpeg", "crop"]
    assert [operation.kind for operation in combined[1].operations] == [
        "screenshot",
        "perspective",
    ]


def test_smoke_plan_uses_feature_rich_positive_and_negative_control():
    full = build_execution_plan(CORPUS, PROFILES, MATRIX, seed=20260827)
    plan = build_execution_plan(
        CORPUS, PROFILES, MATRIX, seed=20260827, smoke=True
    )

    assert [source.fixture_id for source in plan.sources] == [
        "image-clean-noise",
        "negative-external-00",
    ]
    assert plan.candidate_count == 1
    assert plan.attack_count == 9
    assert plan.planned_rows == 18
    assert len(plan.plan_sha256) == 64
    assert plan.plan_sha256 != full.plan_sha256


@pytest.mark.parametrize("fixed_variant", ["empty", "mutated"])
def test_selected_profile_fixed_contract_must_exactly_match_a3(
    bounded_contracts, fixed_variant
):
    corpus, profiles, matrix = bounded_contracts
    document = json.loads(PROFILES.read_text(encoding="utf-8"))
    if fixed_variant == "empty":
        document["fixed"] = {}
    else:
        document["fixed"]["luminance"]["coefficients"][0] = 0.115
    document["sweep"] = {
        "qim_delta": [12.0],
        "tile_size_px": [256],
        "tiles_per_page": [12],
        "payload_repetitions": [3],
    }
    _write_json(profiles, document)

    with pytest.raises(ValueError, match="fixed contract"):
        build_execution_plan(corpus, profiles, matrix, seed=20260827)


def test_candidate_provenance_hash_binds_executed_fixed_and_sweep_values(
    bounded_contracts,
):
    corpus, profiles, matrix = bounded_contracts
    document = json.loads(PROFILES.read_text(encoding="utf-8"))
    document["sweep"] = {
        "qim_delta": [12.0],
        "tile_size_px": [256],
        "tiles_per_page": [12],
        "payload_repetitions": [3],
    }
    _write_json(profiles, document)

    candidate = build_execution_plan(
        corpus, profiles, matrix, seed=20260827
    ).candidates[0]
    expected_document = {
        "schema_version": 1,
        "fixed": document["fixed"],
        "candidate": {
            "qim_delta": 12.0,
            "tile_size_px": 256,
            "tiles_per_page": 12,
            "payload_repetitions": 3,
        },
    }
    expected = hashlib.sha256(
        json.dumps(
            expected_document, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("utf-8")
    ).hexdigest()

    assert candidate.profile_sha256 == expected


def test_checkpoint_resume_is_idempotent_and_reports_partial_state(
    bounded_contracts, tmp_path
):
    corpus, profiles, matrix = bounded_contracts
    output = tmp_path / "resume-output"

    partial = run_matrix(
        corpus, profiles, matrix, seed=20260827, output_dir=output, max_rows=1
    )
    completed = run_matrix(corpus, profiles, matrix, seed=20260827, output_dir=output)
    rows = _read_jsonl(output / "results.jsonl")

    assert partial.status == "partial"
    assert partial.completed_rows == 1
    assert completed.status == "complete"
    assert completed.completed_rows == 2
    assert len(rows) == 2
    assert len({row["row_id"] for row in rows}) == 2
    assert all(row["evidence_scope"] == "research_measurement_only" for row in rows)
    assert all(row["profile_promoted"] is False for row in rows)


def test_completed_plan_with_execution_errors_is_not_reported_as_success(
    bounded_contracts, tmp_path
):
    corpus, profiles, matrix = bounded_contracts
    manifest = json.loads(corpus.read_text(encoding="utf-8"))
    image_path = corpus.parent / manifest["entries"][0]["relative_path"]
    constant = np.zeros((768, 1024, 3), dtype=np.uint8)
    assert cv2.imwrite(str(image_path), constant)
    manifest["entries"][0]["sha256"] = hashlib.sha256(image_path.read_bytes()).hexdigest()
    _write_json(corpus, manifest)

    summary = run_matrix(
        corpus,
        profiles,
        matrix,
        seed=20260827,
        output_dir=tmp_path / "errors",
    )

    assert summary.complete is True
    assert summary.status == "complete_with_errors"
    assert summary.failed_rows == 2
    summary_document = json.loads(
        (tmp_path / "errors" / "summary.json").read_text(encoding="utf-8")
    )
    assert summary_document["detection_metrics"]["eligible_positive_cases"] == 2
    assert summary_document["detection_metrics"]["decode_denominator_positive_cases"] == 2
    assert summary_document["detection_metrics"]["missed_detection"] == 2
    assert summary_document["detection_metrics"]["execution_errors"] == 2
    assert summary_document["detection_metrics"]["decode_rate"] == 0.0


def test_separate_runs_have_identical_normalized_rows_and_stable_csv_order(
    bounded_contracts, tmp_path
):
    corpus, profiles, matrix = bounded_contracts
    output_a = tmp_path / "run-a"
    output_b = tmp_path / "run-b"

    run_matrix(corpus, profiles, matrix, seed=20260827, output_dir=output_a)
    run_matrix(corpus, profiles, matrix, seed=20260827, output_dir=output_b)
    rows_a = _read_jsonl(output_a / "results.jsonl")
    rows_b = _read_jsonl(output_b / "results.jsonl")

    assert _normalized(rows_a) == _normalized(rows_b)
    assert [row["row_id"] for row in rows_a] == sorted(row["row_id"] for row in rows_a)
    with (output_a / "results.csv").open(encoding="utf-8", newline="") as stream:
        csv_rows = list(csv.DictReader(stream))
    assert [row["row_id"] for row in csv_rows] == [row["row_id"] for row in rows_a]


def test_result_rows_carry_required_provenance_metrics_and_explicit_limitations(
    bounded_contracts, tmp_path
):
    corpus, profiles, matrix = bounded_contracts
    output = tmp_path / "evidence"

    run_matrix(corpus, profiles, matrix, seed=20260827, output_dir=output, max_rows=1)
    row = _read_jsonl(output / "results.jsonl")[0]

    assert {
        "corpus_contract_sha256",
        "corpus_sha256",
        "profile_contract_sha256",
        "attack_matrix_sha256",
        "algorithm_profile_sha256",
        "candidate_id",
        "fixture_id",
        "page_index",
        "attack_id",
        "attack_parameters",
        "ordered_operations",
        "seed",
        "case_seed",
        "decoded_id",
        "confidence",
        "bit_error_rate",
        "psnr_db",
        "ssim",
        "localization_iou",
        "elapsed_ms",
        "timing_scope",
        "peak_rss_bytes",
        "peak_rss_scope",
        "temp_peak_bytes",
        "eligible",
        "eligibility_reason",
        "remaining_embedded_tiles",
        "outcome",
        "reason",
        "valid_vote_count",
        "limitations",
    } <= row.keys()
    assert row["timing_scope"] == "attack_and_decode"
    assert row["peak_rss_bytes"] > 0
    assert row["temp_peak_bytes"] == 0
    assert any(
        limitation.startswith("A5 integrity localization is not implemented")
        for limitation in row["limitations"]
    )
    assert row["localization_iou"] is None


def test_rows_compose_source_fit_and_attack_ground_truth_transforms(
    bounded_contracts, tmp_path
):
    corpus, profiles, matrix = bounded_contracts
    source = np.empty((480, 640, 3), dtype=np.uint8)
    y, x = np.indices(source.shape[:2], dtype=np.uint16)
    source[..., 0] = (x + 3 * y) % 256
    source[..., 1] = (5 * x + y) % 256
    source[..., 2] = (2 * x + 7 * y) % 256
    manifest = json.loads(corpus.read_text(encoding="utf-8"))
    image_path = corpus.parent / manifest["entries"][0]["relative_path"]
    assert cv2.imwrite(str(image_path), source)
    manifest["entries"][0]["sha256"] = hashlib.sha256(
        image_path.read_bytes()
    ).hexdigest()
    manifest["entries"][0]["kind"] = "tamper_ground_truth"
    manifest["entries"][0]["ground_truth_regions"] = [
        {"x": 0.2, "y": 0.25, "width": 0.3, "height": 0.25}
    ]
    _write_json(corpus, manifest)
    profile_document = json.loads(profiles.read_text(encoding="utf-8"))
    profile_document["sweep"] = {
        "qim_delta": [12.0],
        "tile_size_px": [384],
        "tiles_per_page": [24],
        "payload_repetitions": [3],
    }
    _write_json(profiles, profile_document)
    matrix_document = json.loads(matrix.read_text(encoding="utf-8"))
    matrix_document["jpeg_quality"] = [95]
    matrix_document["crop_fraction"] = [0.25]
    matrix_document["combined"] = [
        {
            "operations": ["jpeg", "crop"],
            "jpeg_quality": 95,
            "crop_fraction": 0.25,
        }
    ]
    matrix_document["tamper"] = [
        {
            "kind": "cover_region",
            "region": {"x": 0.6, "y": 0.6, "width": 0.1, "height": 0.1},
        }
    ]
    _write_json(matrix, matrix_document)
    output = tmp_path / "ground-truth"

    run_matrix(corpus, profiles, matrix, seed=20260827, output_dir=output)
    rows = {row["attack_kind"]: row for row in _read_jsonl(output / "results.jsonl")}

    fitted_region = {
        "x": 0.23333333333333334,
        "y": 0.25,
        "width": 0.26666666666666666,
        "height": 0.25,
    }
    assert len(rows["jpeg"]["tamper_ground_truth"]) == 1
    assert rows["jpeg"]["tamper_ground_truth"][0] == pytest.approx(fitted_region)
    assert len(rows["tamper"]["tamper_ground_truth"]) == 2
    assert rows["tamper"]["tamper_ground_truth"][0] == pytest.approx(
        fitted_region
    )
    assert rows["tamper"]["tamper_ground_truth"][1] == {
        "x": 0.6,
        "y": 0.6,
        "width": 0.1,
        "height": 0.1,
    }
    cropped_region = {
        "x": 0.19228070175438597,
        "y": 0.2112781954887218,
        "width": 0.30796992481203006,
        "height": 0.2887218045112782,
    }
    assert rows["crop"]["tamper_ground_truth"][0] == pytest.approx(cropped_region)
    assert rows["combined"]["tamper_ground_truth"][0] == pytest.approx(
        cropped_region
    )


def test_committed_pdf_is_renderable_and_page_count_is_not_silently_reduced():
    pages = list(iter_corpus_pages(CORPUS, fixture_ids={"pdf-multi-mixed"}))

    assert len(pages) == 3
    assert [page.page_index for page in pages] == [0, 1, 2]
    assert all(page.image.dtype == np.uint8 for page in pages)
    assert all(page.image.shape[2] == 3 for page in pages)


def test_cli_plan_only_exposes_the_complete_full_matrix_without_claiming_results():
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--profiles",
            str(PROFILES),
            "--corpus",
            str(CORPUS),
            "--matrix",
            str(MATRIX),
            "--seed",
            "20260827",
            "--plan-only",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    plan = json.loads(completed.stdout)
    assert plan == {
        "attack_count": 31,
        "candidate_count": 48,
        "corpus_pages": 22,
        "planned_rows": 32736,
        "seed": 20260827,
        "smoke": False,
    }


def test_cli_executes_a_bounded_matrix_and_reports_artifact_paths(
    bounded_contracts, tmp_path
):
    corpus, profiles, matrix = bounded_contracts
    output = tmp_path / "cli-output"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--profiles",
            str(profiles),
            "--corpus",
            str(corpus),
            "--matrix",
            str(matrix),
            "--seed",
            "20260827",
            "--output",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    summary = json.loads(completed.stdout)
    assert summary["status"] == "complete"
    assert summary["completed_rows"] == 2
    assert Path(summary["output_dir"]) == output.resolve()
    assert (output / "summary.json").is_file()
