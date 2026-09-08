import json
import math
import hashlib
from pathlib import Path
import shutil
import struct
import subprocess
import sys
from uuid import UUID

import pytest

from splitbind_bench.promotion import (
    BenchmarkSummary,
    ProfileScore,
    aggregate_profile_scores,
    eligible_profiles,
    ensure_release_absent,
    load_benchmark_summary,
    NoEligibleProfile,
    NonPromotableBenchmark,
    promote_profile,
    write_evaluation_report,
)
from splitbind_bench.runner import build_execution_plan
from splitbind_ref.tile_layout import derive_tiles


ROOT = Path(__file__).resolve().parents[4]
PROFILES = ROOT / "contracts" / "algorithm" / "fingerprint-candidates.v1.json"
CORPUS = ROOT / "fixtures" / "corpus" / "corpus-manifest.v1.json"
MATRIX = ROOT / "contracts" / "algorithm" / "attack-matrix.v1.json"
PROMOTE_SCRIPT = ROOT / "research" / "python" / "scripts" / "promote_profile.py"


def _profile(
    profile_id: str,
    *,
    false_attribution: int = 0,
    jpeg70_rate: float = 1.0,
    resize075_rate: float = 1.0,
    crop025_rate: float = 1.0,
    ssim: float = 0.96,
    psnr: float = 39.0,
    milliseconds: float = 400.0,
) -> ProfileScore:
    return ProfileScore(
        profile_id=profile_id,
        candidate_id=f"candidate-{profile_id}",
        false_attribution=false_attribution,
        execution_errors=0,
        scheduled_rows=682,
        jpeg70_true_attribution=12,
        jpeg70_denominator=12,
        jpeg70_rate=jpeg70_rate,
        resize075_true_attribution=12,
        resize075_denominator=12,
        resize075_rate=resize075_rate,
        crop025_true_attribution=12,
        crop025_denominator=12,
        crop025_rate=crop025_rate,
        quality_observations=12,
        mean_psnr_db=psnr,
        mean_ssim=ssim,
        processing_observations=682,
        processing_ms_per_page=milliseconds,
        failed_gates=(),
    )


def _summary(*profiles: ProfileScore) -> BenchmarkSummary:
    return BenchmarkSummary(
        schema_version=1,
        status="complete",
        seed=20260827,
        corpus_pages=22,
        candidate_count=48,
        attack_count=31,
        planned_rows=32736,
        completed_rows=32736,
        execution_errors=0,
        contract_hashes={
            "corpus_sha256": "e5837cd446ab9c9959ba3fc4b85d205ec9d80e91efc6f801d139810b088a77ef",
            "profiles_sha256": "d3a8c2ec271c76a2ed424dd52fc5f2760ddd3ef2773663168bbad68e54865e9f",
            "attack_matrix_sha256": "fb3c485d45df15b5f16f76e888be0c2d443d2433ba35cdb1df06a85881a6d40e",
        },
        plan_sha256="9118eb9424e32400548d7feae4cb5d9c9c827359d9d8b74a6d9e3a9f0d7f71f3",
        results_sha256="2" * 64,
        source_summary_sha256="3" * 64,
        profiles=profiles,
        limitations=(),
        execution_error_details=(),
    )


def test_profile_with_false_attribution_is_ineligible():
    summary = _summary(_profile("a", false_attribution=1))

    assert eligible_profiles(summary) == ()


def test_best_eligible_profile_prefers_quality_then_speed():
    summary = _summary(
        _profile("a", ssim=0.961, psnr=39.0, milliseconds=400),
        _profile("b", ssim=0.970, psnr=39.2, milliseconds=500),
    )

    assert eligible_profiles(summary)[0].profile_id == "b"


@pytest.mark.parametrize(("status", "execution_errors"), [("partial", 0), ("complete_with_errors", 1), ("complete", 1)])
def test_public_eligibility_api_rejects_non_complete_or_error_run(status, execution_errors):
    source = _summary(_profile("a"))
    summary = BenchmarkSummary(
        **{
            field: getattr(source, field)
            for field in source.__dataclass_fields__
            if field not in {"status", "execution_errors"}
        },
        status=status,
        execution_errors=execution_errors,
    )

    with pytest.raises((NonPromotableBenchmark, ValueError), match="complete|execution error"):
        eligible_profiles(summary)


def test_nonpromotable_evidence_cannot_be_passed_directly_to_promote(tmp_path):
    source = _summary(_profile("a"))
    evidence = BenchmarkSummary(
        **{
            field: getattr(source, field)
            for field in source.__dataclass_fields__
            if field not in {"status", "execution_errors"}
        },
        status="complete_with_errors",
        execution_errors=1,
    )
    captured = NonPromotableBenchmark(evidence)
    output = tmp_path / "fingerprint-profile.v1.json"

    with pytest.raises(NonPromotableBenchmark):
        promote_profile(captured.evidence, PROFILES, output)

    assert not output.exists()


def _row(
    *,
    profile_id: str = "profile-a",
    candidate_id: str = "candidate-a",
    fixture_id: str = "positive",
    page_index: int = 0,
    fixture_kind: str = "clean_image",
    attack_id: str = "jpeg-q70",
    attack_kind: str = "jpeg",
    attack_parameters=None,
    expected_id: str | None = "expected-a",
    decoded_id: str | None = "expected-a",
    reason: str = "decoded",
    eligible: bool = True,
    remaining_embedded_tiles: int | None = None,
    eligibility_reason: str = "eligible",
    psnr_db: float = 39.0,
    ssim: float = 0.96,
    elapsed_ms: float = 10.0,
):
    return {
        "row_id": f"{profile_id}:{fixture_id}:{page_index}:{attack_id}",
        "algorithm_profile_sha256": profile_id,
        "candidate_id": candidate_id,
        "fixture_id": fixture_id,
        "fixture_kind": fixture_kind,
        "page_index": page_index,
        "attack_id": attack_id,
        "attack_kind": attack_kind,
        "attack_parameters": attack_parameters
        if attack_parameters is not None
        else {"quality": 70},
        "expected_id": expected_id,
        "decoded_id": decoded_id,
        "reason": reason,
        "eligible": eligible,
        "remaining_embedded_tiles": remaining_embedded_tiles,
        "eligibility_reason": eligibility_reason,
        "psnr_db": psnr_db,
        "ssim": ssim,
        "quality_scope": "original_vs_watermarked_before_attack"
        if expected_id is not None
        else "negative_control_original_vs_unmodified",
        "quality_data_range": 255.0,
        "elapsed_ms": elapsed_ms,
        "limitations": [],
    }


def test_row_aggregation_uses_exact_denominators_and_unique_clean_quality():
    rows = [
        _row(attack_id="jpeg-q70-ok", elapsed_ms=10.0),
        _row(
            fixture_id="positive-2",
            attack_id="jpeg-q70-wrong",
            decoded_id="wrong",
            elapsed_ms=20.0,
        ),
        _row(
            fixture_id="positive-3",
            attack_id="jpeg-q70-error",
            decoded_id=None,
            reason="execution_error",
            eligible=False,
            elapsed_ms=30.0,
        ),
        _row(
            fixture_id="positive",
            attack_id="resize-s0p75",
            attack_kind="resize",
            attack_parameters={"scale": 0.75},
            elapsed_ms=40.0,
        ),
        _row(
            fixture_id="positive",
            attack_id="crop-f0p25",
            attack_kind="crop",
            attack_parameters={"fraction": 0.25},
            elapsed_ms=50.0,
        ),
        _row(
            fixture_id="positive-2",
            attack_id="crop-f0p25-ineligible",
            attack_kind="crop",
            attack_parameters={"fraction": 0.25},
            decoded_id="wrong-crop-id",
            eligible=False,
            elapsed_ms=60.0,
        ),
        _row(
            fixture_id="negative",
            fixture_kind="negative_external",
            attack_id="jpeg-q70-negative",
            expected_id=None,
            decoded_id="wrong-negative-id",
            elapsed_ms=70.0,
        ),
    ]

    score = aggregate_profile_scores(rows)[0]

    assert score.false_attribution == 3
    assert score.execution_errors == 1
    assert (score.jpeg70_true_attribution, score.jpeg70_denominator) == (1, 3)
    assert score.jpeg70_rate == pytest.approx(1.0 / 3.0)
    assert (score.resize075_true_attribution, score.resize075_denominator) == (1, 1)
    assert score.resize075_rate == 1.0
    assert (score.crop025_true_attribution, score.crop025_denominator) == (1, 1)
    assert score.crop025_rate == 1.0
    assert score.quality_observations == 2
    assert score.mean_psnr_db == 39.0
    assert score.mean_ssim == 0.96
    assert score.processing_observations == 7
    assert score.processing_ms_per_page == 40.0
    assert score.failed_gates == (
        "benchmark_execution_errors_zero",
        "false_attribution_zero",
        "jpeg70_decode_rate_at_least_0.95",
        "complete_quality_population_12",
    )


def test_execution_error_with_matching_decoded_id_is_a_required_gate_miss():
    score = aggregate_profile_scores(
        [_row(reason="execution_error", decoded_id="expected-a")]
    )[0]

    assert (score.jpeg70_true_attribution, score.jpeg70_denominator) == (0, 1)
    assert score.jpeg70_rate == 0.0


@pytest.mark.parametrize(
    ("field", "value"),
    [("ssim", math.nan), ("psnr_db", math.inf), ("elapsed_ms", -1.0)],
)
def test_row_aggregation_rejects_non_finite_or_negative_measurements(field, value):
    row = _row()
    row[field] = value

    with pytest.raises(ValueError, match="finite|non-negative"):
        aggregate_profile_scores([row])


def test_quality_observation_repetition_must_be_identical():
    rows = [
        _row(attack_id="jpeg-q70"),
        _row(
            attack_id="resize-s0p75",
            attack_kind="resize",
            attack_parameters={"scale": 0.75},
            psnr_db=38.5,
        ),
    ]

    with pytest.raises(ValueError, match="quality observation"):
        aggregate_profile_scores(rows)


@pytest.mark.parametrize(
    "mutation",
    [
        {"false_attribution": 1},
        {"jpeg70_rate": 0.949999},
        {"resize075_rate": 0.949999},
        {"crop025_rate": 0.899999},
        {"psnr": 37.999},
        {"ssim": 0.949999},
    ],
)
def test_each_gate_rejects_just_below_its_exact_boundary(mutation):
    assert eligible_profiles(_summary(_profile("a", **mutation))) == ()


def test_exact_gate_boundaries_are_eligible():
    score = _profile(
        "boundary",
        jpeg70_rate=0.95,
        resize075_rate=0.95,
        crop025_rate=0.90,
        psnr=38.0,
        ssim=0.95,
    )

    assert eligible_profiles(_summary(score)) == (score,)


def _geometry_truth(candidate, fixture_id, page_index, attack, expected_id, reason):
    if expected_id is None or reason == "execution_error":
        return True, None, "eligible"
    crop = attack if attack.kind == "crop" else next(
        (operation for operation in attack.operations if operation.kind == "crop"), None
    )
    if crop is None:
        return True, None, "eligible"
    width, height = 2304, 1536
    side_scale = math.sqrt(1.0 - float(crop.parameters["fraction"]))
    retained_width = max(1, round(width * side_scale))
    retained_height = max(1, round(height * side_scale))
    x0 = (width - retained_width) // 2
    y0 = (height - retained_height) // 2
    binding = (
        (20260827).to_bytes(8, "big")
        + fixture_id.encode()
        + b"\0"
        + page_index.to_bytes(4, "big")
        + bytes.fromhex(candidate.profile_sha256)
    )
    key = hashlib.sha256(b"splitbind-benchmark-key-v1\0" + binding).digest()
    nonce = hashlib.sha256(b"splitbind-benchmark-nonce-v1\0" + binding).digest()[:16]
    profile = {
        "schema_version": 1,
        **candidate.values,
        "document_nonce": nonce,
        "page_index": page_index,
    }
    tiles = derive_tiles(
        (height, width),
        key,
        nonce,
        page_index,
        {
            "schema_version": 1,
            "tile_size_px": int(candidate.values["tile_size_px"]),
            "tiles_per_page": int(candidate.values["tiles_per_page"]),
        },
    )[: int(profile["payload_repetitions"])]
    remaining = sum(
        tile.x >= x0
        and tile.y >= y0
        and tile.x + tile.width <= x0 + retained_width
        and tile.y + tile.height <= y0 + retained_height
        for tile in tiles
    )
    eligible = remaining >= 2
    reason_text = (
        "at_least_two_complete_embedded_tiles_remain"
        if eligible
        else "fewer_than_two_complete_embedded_tiles_remain"
    )
    return eligible, remaining, reason_text


@pytest.fixture(scope="module")
def complete_evidence(tmp_path_factory):
    output = tmp_path_factory.mktemp("complete-promotion-evidence")
    plan = build_execution_plan(CORPUS, PROFILES, MATRIX, seed=20260827)
    summary = {
        "schema_version": 1,
        "status": "complete",
        "complete": True,
        "planned_rows": 32736,
        "planned_shard_rows": 32736,
        "completed_rows": 32736,
        "failed_rows": 0,
        "seed": 20260827,
        "smoke": False,
        "shard_index": 0,
        "shard_count": 1,
        "contracts": {
            "corpus_sha256": plan.corpus_contract_sha256,
            "profiles_sha256": plan.profile_contract_sha256,
            "attack_matrix_sha256": plan.attack_matrix_sha256,
            "plan_sha256": plan.plan_sha256,
        },
        "limitations": ["synthetic complete evidence for promotion tests"],
    }
    summary_path = output / "summary.json"
    summary_path.write_text(json.dumps(summary, sort_keys=True), encoding="utf-8")
    results_path = output / "results.jsonl"
    with results_path.open("w", encoding="utf-8", newline="\n") as stream:
        for candidate_index, candidate in enumerate(plan.candidates):
            values = candidate.values
            candidate_id = (
                b"SBFP\x01"
                + struct.pack(
                    ">IdIII",
                    1,
                    values["qim_delta"],
                    values["tile_size_px"],
                    values["tiles_per_page"],
                    values["payload_repetitions"],
                )
            ).hex()
            for source in plan.sources:
                for page_index in range(source.pages):
                    if source.kind == "negative_external":
                        expected_id = None
                    else:
                        binding = (
                            (20260827).to_bytes(8, "big")
                            + source.fixture_id.encode()
                            + b"\0"
                            + page_index.to_bytes(4, "big")
                            + bytes.fromhex(candidate.profile_sha256)
                        )
                        issuance = bytearray(
                            hashlib.sha256(
                                b"splitbind-benchmark-identity-v1\0" + binding
                            ).digest()[:16]
                        )
                        issuance[6] = (issuance[6] & 0x0F) | 0x40
                        issuance[8] = (issuance[8] & 0x3F) | 0x80
                        expected_id = str(UUID(bytes=bytes(issuance)))
                    for attack in plan.attacks:
                        reason = "decoded" if expected_id is not None else "not_detected"
                        eligible, remaining, eligibility_reason = _geometry_truth(
                            candidate,
                            source.fixture_id,
                            page_index,
                            attack,
                            expected_id,
                            reason,
                        )
                        row = _row(
                            profile_id=candidate.profile_sha256,
                            candidate_id=candidate_id,
                            fixture_id=source.fixture_id,
                            page_index=page_index,
                            fixture_kind=source.kind,
                            attack_id=attack.case_id,
                            attack_kind=attack.kind,
                            attack_parameters=json.loads(
                                json.dumps(attack.parameters, default=list)
                            ),
                            expected_id=expected_id,
                            decoded_id=expected_id,
                            reason=reason,
                            eligible=eligible,
                            remaining_embedded_tiles=remaining,
                            eligibility_reason=eligibility_reason,
                            psnr_db=39.0 + candidate_index / 1000.0,
                            ssim=0.96 + candidate_index / 100000.0,
                            elapsed_ms=100.0 - candidate_index / 10.0,
                        )
                        row.update(
                            {
                                "schema_version": 1,
                                "corpus_contract_sha256": plan.corpus_contract_sha256,
                                "profile_contract_sha256": plan.profile_contract_sha256,
                                "attack_matrix_sha256": plan.attack_matrix_sha256,
                                "benchmark_plan_sha256": plan.plan_sha256,
                                "seed": 20260827,
                                "outcome": "true_attribution"
                                if expected_id is not None
                                else "true_negative",
                            }
                        )
                        row["row_id"] = hashlib.sha256(
                            (
                                f"{source.fixture_id}\0{page_index}\0"
                                f"{candidate.profile_sha256}\0{attack.case_id}"
                            ).encode()
                        ).hexdigest()
                        stream.write(json.dumps(row, sort_keys=True) + "\n")
    return summary_path, results_path, summary


def test_complete_exact_run_is_reaggregated_from_all_rows(complete_evidence):
    summary_path, _, _ = complete_evidence

    loaded = load_benchmark_summary(summary_path, PROFILES)

    assert loaded.completed_rows == 32736
    assert loaded.execution_errors == 0
    assert len(loaded.profiles) == 48
    assert all(score.scheduled_rows == 682 for score in loaded.profiles)
    assert all(score.quality_observations == 12 for score in loaded.profiles)
    assert all(score.jpeg70_denominator == 12 for score in loaded.profiles)
    assert all(score.resize075_denominator == 12 for score in loaded.profiles)
    assert all(0 < score.crop025_denominator <= 12 for score in loaded.profiles)


def test_same_plan_from_substituted_contract_bytes_is_rejected(complete_evidence, tmp_path):
    _, results_path, source_summary = complete_evidence
    corpus_dir = tmp_path / "corpus"
    shutil.copytree(CORPUS.parent, corpus_dir)
    corpus = corpus_dir / CORPUS.name
    profiles = tmp_path / PROFILES.name
    matrix = tmp_path / MATRIX.name
    profiles.write_bytes(PROFILES.read_bytes() + b"\n")
    matrix.write_bytes(MATRIX.read_bytes() + b"\n")
    corpus.write_bytes(corpus.read_bytes() + b"\n")
    substituted = build_execution_plan(corpus, profiles, matrix, seed=20260827)
    assert substituted.plan_sha256 == source_summary["contracts"]["plan_sha256"]
    summary = json.loads(json.dumps(source_summary))
    summary["contracts"] = {
        "corpus_sha256": substituted.corpus_contract_sha256,
        "profiles_sha256": substituted.profile_contract_sha256,
        "attack_matrix_sha256": substituted.attack_matrix_sha256,
        "plan_sha256": substituted.plan_sha256,
    }
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    rows = results_path.read_text(encoding="utf-8")
    rows = rows.replace(
        source_summary["contracts"]["corpus_sha256"], substituted.corpus_contract_sha256
    ).replace(
        source_summary["contracts"]["profiles_sha256"], substituted.profile_contract_sha256
    ).replace(
        source_summary["contracts"]["attack_matrix_sha256"], substituted.attack_matrix_sha256
    )
    (tmp_path / "results.jsonl").write_text(rows, encoding="utf-8")

    with pytest.raises(ValueError, match="pinned|baseline"):
        load_benchmark_summary(summary_path, profiles, corpus=corpus, matrix=matrix)


def test_same_cardinality_substituted_plan_sha_is_rejected(complete_evidence, tmp_path):
    _, results_path, source_summary = complete_evidence
    matrix_document = json.loads(MATRIX.read_text(encoding="utf-8"))
    matrix_document["brightness_contrast"][0]["brightness_factor"] = 0.86
    matrix = tmp_path / MATRIX.name
    matrix.write_text(json.dumps(matrix_document), encoding="utf-8")
    substituted = build_execution_plan(CORPUS, PROFILES, matrix, seed=20260827)
    assert substituted.planned_rows == 32736
    assert substituted.plan_sha256 != source_summary["contracts"]["plan_sha256"]
    summary = json.loads(json.dumps(source_summary))
    summary["contracts"]["attack_matrix_sha256"] = substituted.attack_matrix_sha256
    summary["contracts"]["plan_sha256"] = substituted.plan_sha256
    changed = []
    for line in results_path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        row["attack_matrix_sha256"] = substituted.attack_matrix_sha256
        row["benchmark_plan_sha256"] = substituted.plan_sha256
        if row["attack_id"] == "brightness-contrast-0":
            row["attack_parameters"]["brightness_factor"] = 0.86
        changed.append(json.dumps(row, sort_keys=True))
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    (tmp_path / "results.jsonl").write_text("\n".join(changed) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="pinned|baseline"):
        load_benchmark_summary(summary_path, PROFILES, matrix=matrix)


@pytest.mark.parametrize("field", ["eligible", "remaining_embedded_tiles", "eligibility_reason"])
def test_crop_geometry_fields_must_exactly_match_reconstructed_truth(
    complete_evidence, tmp_path, field
):
    _, results_path, source_summary = complete_evidence
    rows = results_path.read_text(encoding="utf-8").splitlines()
    for index, encoded in enumerate(rows):
        row = json.loads(encoded)
        if row["expected_id"] is not None and row["attack_id"] == "crop-f0p25":
            if field == "eligible":
                row[field] = not row[field]
            elif field == "remaining_embedded_tiles":
                row[field] += 1
            else:
                row[field] = {
                    "eligible": "fewer_than_two_complete_embedded_tiles_remain",
                    "at_least_two_complete_embedded_tiles_remain": "fewer_than_two_complete_embedded_tiles_remain",
                    "fewer_than_two_complete_embedded_tiles_remain": "at_least_two_complete_embedded_tiles_remain",
                }[row["eligibility_reason"]]
            rows[index] = json.dumps(row, sort_keys=True)
            break
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps(source_summary), encoding="utf-8")
    (tmp_path / "results.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="eligib|remaining|geometry"):
        load_benchmark_summary(summary_path, PROFILES)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("status", "partial", "complete"),
        ("completed_rows", 32735, "32,736"),
        ("shard_count", 2, "unsharded"),
        ("failed_rows", 1, "execution error"),
        ("seed", 1, "seed"),
    ],
)
def test_partial_sharded_error_or_wrong_seed_summary_is_rejected(
    complete_evidence, tmp_path, field, value, message
):
    _, results_path, source_summary = complete_evidence
    summary = dict(source_summary)
    summary[field] = value
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    (tmp_path / "results.jsonl").write_bytes(results_path.read_bytes())

    with pytest.raises(ValueError, match=message):
        load_benchmark_summary(summary_path, PROFILES)


def test_duplicate_row_is_rejected_even_when_total_count_matches(complete_evidence, tmp_path):
    _, results_path, source_summary = complete_evidence
    rows = results_path.read_text(encoding="utf-8").splitlines()
    rows[-1] = rows[0]
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps(source_summary), encoding="utf-8")
    (tmp_path / "results.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate"):
        load_benchmark_summary(summary_path, PROFILES)


def test_contract_hash_mismatch_is_rejected_before_scoring(complete_evidence, tmp_path):
    _, results_path, source_summary = complete_evidence
    summary = json.loads(json.dumps(source_summary))
    summary["contracts"]["corpus_sha256"] = "0" * 64
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    (tmp_path / "results.jsonl").write_bytes(results_path.read_bytes())

    with pytest.raises(ValueError, match="contract|checksum"):
        load_benchmark_summary(summary_path, PROFILES)


def test_boolean_summary_schema_version_is_rejected(complete_evidence, tmp_path):
    _, results_path, source_summary = complete_evidence
    summary = dict(source_summary)
    summary["schema_version"] = True
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    (tmp_path / "results.jsonl").write_bytes(results_path.read_bytes())

    with pytest.raises(ValueError, match="schema_version"):
        load_benchmark_summary(summary_path, PROFILES)


def test_summary_duplicate_security_key_is_rejected(complete_evidence, tmp_path):
    _, results_path, source_summary = complete_evidence
    encoded = json.dumps(source_summary)
    encoded = encoded.replace(
        '"status": "complete"', '"status": "partial", "status": "complete"', 1
    )
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(encoded, encoding="utf-8")
    (tmp_path / "results.jsonl").write_bytes(results_path.read_bytes())

    with pytest.raises(ValueError, match="duplicate|strict JSON"):
        load_benchmark_summary(summary_path, PROFILES)


def test_jsonl_nested_duplicate_attack_parameter_is_rejected(complete_evidence, tmp_path):
    _, results_path, source_summary = complete_evidence
    rows = results_path.read_text(encoding="utf-8").splitlines()
    assert '"attack_parameters": {"quality": 95}' in rows[0]
    rows[0] = rows[0].replace(
        '"attack_parameters": {"quality": 95}',
        '"attack_parameters": {"quality": 1, "quality": 95}',
        1,
    )
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps(source_summary), encoding="utf-8")
    (tmp_path / "results.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate|strict JSON"):
        load_benchmark_summary(summary_path, PROFILES)


def test_wrong_unsigned_quality_dynamic_range_is_rejected(complete_evidence, tmp_path):
    _, results_path, source_summary = complete_evidence
    rows = results_path.read_text(encoding="utf-8").splitlines()
    first = json.loads(rows[0])
    first["quality_data_range"] = 65535.0
    rows[0] = json.dumps(first, sort_keys=True)
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps(source_summary), encoding="utf-8")
    (tmp_path / "results.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unsigned dynamic range"):
        load_benchmark_summary(summary_path, PROFILES)


def test_release_copies_fixed_candidate_provenance_gates_and_selection_deterministically(
    complete_evidence, tmp_path
):
    summary_path, _, _ = complete_evidence
    summary = load_benchmark_summary(summary_path, PROFILES)
    output = tmp_path / "fingerprint-profile.v1.json"

    released = promote_profile(summary, PROFILES, output)
    first_bytes = output.read_bytes()
    repeated = promote_profile(summary, PROFILES, output)

    assert repeated == released
    assert output.read_bytes() == first_bytes
    document = json.loads(first_bytes)
    candidates = json.loads(PROFILES.read_text(encoding="utf-8"))
    assert document["schema_version"] == 1
    assert document["profile_version"] == 1
    assert document["fixed"] == candidates["fixed"]
    assert document["candidate"] == {
        "payload_repetitions": 5,
        "qim_delta": 12.0,
        "tile_size_px": 384,
        "tiles_per_page": 24,
    }
    assert document["candidate_provenance"]["algorithm_profile_sha256"] == released.profile_id
    assert document["benchmark"]["planned_rows"] == 32736
    assert document["benchmark"]["baseline_requirements_version"] == 1
    assert document["benchmark"]["results_sha256"] == summary.results_sha256
    assert document["gate_measurements"]["quality_observations"] == 12
    assert document["gate_measurements"]["quality"] == {
        "data_range": 255,
        "data_range_units": "uint8_unsigned_intensity_levels",
        "mean_psnr": {
            "denominator_observations": 12,
            "threshold": 38.0,
            "units": "dB",
            "value": document["gate_measurements"]["mean_psnr_db"]["value"],
        },
        "mean_ssim": {
            "denominator_observations": 12,
            "threshold": 0.95,
            "units": "dimensionless",
            "value": document["gate_measurements"]["mean_ssim"]["value"],
        },
        "population_denominator": "unique_positive_candidate_page_pairs",
        "population_observations": 12,
        "required_population": 12,
        "scope": "original_vs_watermarked_before_attack",
    }
    assert document["gate_measurements"]["jpeg70"]["denominator_positive_pages"] == 12
    assert document["selection"]["ordering"] == [
        "highest_mean_ssim",
        "highest_worst_required_decode_rate",
        "lowest_attack_and_decode_ms_per_page",
        "algorithm_profile_sha256_ascending",
    ]


def test_release_refuses_to_overwrite_different_existing_bytes(complete_evidence, tmp_path):
    summary = load_benchmark_summary(complete_evidence[0], PROFILES)
    output = tmp_path / "fingerprint-profile.v1.json"
    output.write_text("user-owned-content", encoding="utf-8")

    with pytest.raises(FileExistsError, match="different bytes"):
        promote_profile(summary, PROFILES, output)

    assert output.read_text(encoding="utf-8") == "user-owned-content"


def test_stale_release_cleanup_unlinks_only_the_named_symlink(tmp_path):
    target = tmp_path / "preserved-target.json"
    target.write_text("preserve", encoding="utf-8")
    link = tmp_path / "fingerprint-profile.v1.json"
    try:
        link.symlink_to(target)
    except OSError as error:
        pytest.skip(f"symlinks unavailable: {error}")

    ensure_release_absent(link)

    assert not link.exists()
    assert target.read_text(encoding="utf-8") == "preserve"


def test_evaluation_report_is_deterministic_and_covers_all_candidates(complete_evidence, tmp_path):
    summary = load_benchmark_summary(complete_evidence[0], PROFILES)
    output = tmp_path / "report.md"
    released = promote_profile(summary, PROFILES, tmp_path / "profile.json")

    write_evaluation_report(summary, output, released)
    first = output.read_bytes()
    write_evaluation_report(summary, output, released)

    assert output.read_bytes() == first
    text = first.decode("utf-8")
    assert "32,736" in text
    assert "Baseline requirements version: `1`" in text
    assert "12 clean watermarked positive pages" in text
    assert "`original_vs_watermarked_before_attack`" in text
    assert "data range is exactly `255` uint8 unsigned intensity levels" in text
    assert "denominator is exactly 12 unique positive candidate/page pairs" in text
    assert "PSNR is measured in dB; SSIM is dimensionless" in text
    assert "Released" in text
    assert sum(line.startswith("| `") for line in text.splitlines()) == 48


def _make_no_eligible_evidence(complete_evidence, destination):
    _, results_path, source_summary = complete_evidence
    seen = set()
    changed = []
    for line in results_path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        profile_id = row["algorithm_profile_sha256"]
        if row["expected_id"] is not None and profile_id not in seen:
            row["decoded_id"] = "00000000-0000-4000-8000-000000000000"
            row["outcome"] = "false_attribution"
            seen.add(profile_id)
        changed.append(json.dumps(row, sort_keys=True))
    assert len(seen) == 48
    summary_path = destination / "summary.json"
    summary_path.write_text(json.dumps(source_summary), encoding="utf-8")
    (destination / "results.jsonl").write_text(
        "\n".join(changed) + "\n", encoding="utf-8"
    )
    return summary_path


def test_no_eligible_cli_is_nonzero_removes_stale_release_and_writes_all_failures(
    complete_evidence, tmp_path
):
    summary_path = _make_no_eligible_evidence(complete_evidence, tmp_path)
    output = tmp_path / "fingerprint-profile.v1.json"
    output.write_text("stale", encoding="utf-8")
    report = tmp_path / "evaluation.md"

    completed = subprocess.run(
        [
            sys.executable,
            str(PROMOTE_SCRIPT),
            "--summary",
            str(summary_path),
            "--candidates",
            str(PROFILES),
            "--output",
            str(output),
            "--report",
            str(report),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "no eligible" in (completed.stdout + completed.stderr).lower()
    assert not output.exists()
    text = report.read_text(encoding="utf-8")
    assert "No release" in text
    assert text.count("false_attribution_zero") == 48


def test_success_cli_writes_release_and_report(complete_evidence, tmp_path):
    output = tmp_path / "fingerprint-profile.v1.json"
    report = tmp_path / "evaluation.md"

    completed = subprocess.run(
        [
            sys.executable,
            str(PROMOTE_SCRIPT),
            "--summary",
            str(complete_evidence[0]),
            "--candidates",
            str(PROFILES),
            "--output",
            str(output),
            "--report",
            str(report),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert output.is_file()
    assert report.is_file()
    assert json.loads(completed.stdout)["status"] == "released"


@pytest.mark.parametrize("failure", ["malformed", "partial", "mismatch"])
def test_cli_every_validation_failure_removes_exact_stale_release(
    complete_evidence, tmp_path, failure
):
    _, results_path, source_summary = complete_evidence
    summary_path = tmp_path / "summary.json"
    if failure == "malformed":
        summary_path.write_text('{"status":', encoding="utf-8")
    else:
        summary = json.loads(json.dumps(source_summary))
        if failure == "partial":
            summary["status"] = "partial"
        else:
            summary["contracts"]["plan_sha256"] = "0" * 64
        summary_path.write_text(json.dumps(summary), encoding="utf-8")
        (tmp_path / "results.jsonl").write_bytes(results_path.read_bytes())
    output = tmp_path / "fingerprint-profile.v1.json"
    output.write_text("stale", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(PROMOTE_SCRIPT),
            "--summary",
            str(summary_path),
            "--candidates",
            str(PROFILES),
            "--output",
            str(output),
            "--report",
            str(tmp_path / "evaluation.md"),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert not output.exists()


def test_cli_report_finalization_failure_leaves_no_release(complete_evidence, tmp_path):
    output = tmp_path / "fingerprint-profile.v1.json"
    report = tmp_path / "evaluation.md"
    report.mkdir()

    completed = subprocess.run(
        [
            sys.executable,
            str(PROMOTE_SCRIPT),
            "--summary",
            str(complete_evidence[0]),
            "--candidates",
            str(PROFILES),
            "--output",
            str(output),
            "--report",
            str(report),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert not output.exists()


def test_cli_output_parent_failure_is_caught_and_reported(complete_evidence, tmp_path):
    blocked_parent = tmp_path / "not-a-directory"
    blocked_parent.write_text("preserve", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(PROMOTE_SCRIPT),
            "--summary",
            str(complete_evidence[0]),
            "--candidates",
            str(PROFILES),
            "--output",
            str(blocked_parent / "fingerprint-profile.v1.json"),
            "--report",
            str(tmp_path / "evaluation.md"),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 2
    assert "promotion rejected" in completed.stderr
    assert "Traceback" not in completed.stderr
    assert blocked_parent.read_text(encoding="utf-8") == "preserve"


def test_cli_validation_failure_unlinks_only_named_release_symlink(tmp_path):
    target = tmp_path / "preserved-target.json"
    target.write_text("preserve", encoding="utf-8")
    output = tmp_path / "fingerprint-profile.v1.json"
    try:
        output.symlink_to(target)
    except OSError as error:
        pytest.skip(f"symlinks unavailable: {error}")
    malformed = tmp_path / "summary.json"
    malformed.write_text("{", encoding="utf-8")

    completed = subprocess.run(
        [
            sys.executable,
            str(PROMOTE_SCRIPT),
            "--summary",
            str(malformed),
            "--candidates",
            str(PROFILES),
            "--output",
            str(output),
            "--report",
            str(tmp_path / "evaluation.md"),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert not output.exists()
    assert target.read_text(encoding="utf-8") == "preserve"


def test_complete_with_errors_cli_rejects_release_but_writes_factual_report(
    complete_evidence, tmp_path
):
    _, results_path, source_summary = complete_evidence
    seen = set()
    changed = []
    for line in results_path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        profile_id = row["algorithm_profile_sha256"]
        if row["expected_id"] is not None and profile_id not in seen:
            row["decoded_id"] = None
            row["reason"] = "execution_error"
            row["outcome"] = "execution_error"
            row["limitations"] = ["embedding ValueError: synthetic feature failure"]
            seen.add(profile_id)
        changed.append(json.dumps(row, sort_keys=True))
    assert len(seen) == 48
    summary = dict(source_summary)
    summary.update({"status": "complete_with_errors", "failed_rows": 48})
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    (tmp_path / "results.jsonl").write_text(
        "\n".join(changed) + "\n", encoding="utf-8"
    )
    output = tmp_path / "fingerprint-profile.v1.json"
    output.write_text("stale", encoding="utf-8")
    report = tmp_path / "evaluation.md"

    completed = subprocess.run(
        [
            sys.executable,
            str(PROMOTE_SCRIPT),
            "--summary",
            str(summary_path),
            "--candidates",
            str(PROFILES),
            "--output",
            str(output),
            "--report",
            str(report),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "complete_with_errors" in (completed.stdout + completed.stderr)
    assert not output.exists()
    text = report.read_text(encoding="utf-8")
    assert "No release" in text
    assert "48 execution errors" in text
    assert "embedding ValueError: synthetic feature failure" in text
    assert text.count("benchmark_execution_errors_zero") == 48
