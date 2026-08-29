import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from splitbind_bench.integrity_runner import run_integrity_matrix


ROOT = Path(__file__).resolve().parents[4]


def test_integrity_only_matrix_is_deterministic_and_records_fail_closed_denominators(
    tmp_path,
):
    y, x = np.indices((512, 512), dtype=np.uint16)
    image = np.empty((512, 512, 3), dtype=np.uint8)
    image[..., 0] = (x * 3 + y) % 256
    image[..., 1] = (x + y * 5) % 256
    image[..., 2] = (x * 7 + y * 2) % 256
    image_path = tmp_path / "page.png"
    assert cv2.imwrite(str(image_path), image)
    image_sha256 = hashlib.sha256(image_path.read_bytes()).hexdigest()
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "entries": [
                    {
                        "fixture_id": "one-page",
                        "kind": "clean_image",
                        "relative_path": "page.png",
                        "sha256": image_sha256,
                        "pages": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    matrix_path = tmp_path / "matrix.json"
    matrix_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "tamper": [
                    {
                        "kind": "cover_region",
                        "region": {
                            "x": 0.25,
                            "y": 0.25,
                            "width": 0.25,
                            "height": 0.25,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    profile_path = ROOT / "contracts/algorithm/integrity-profile.v1.json"
    output = tmp_path / "report"
    evaluation = tmp_path / "evaluation.md"
    command = (
        "python research/python/scripts/run_integrity_benchmark.py "
        "--corpus corpus.json --profile integrity-profile.v1.json "
        "--matrix matrix.json --seed 20260827 --output report "
        "--evaluation evaluation.md"
    )

    first = run_integrity_matrix(
        corpus_path,
        profile_path,
        matrix_path,
        20260827,
        output,
        evaluation,
        command=command,
    )
    first_json = (output / "summary.json").read_bytes()
    first_markdown = evaluation.read_bytes()
    second = run_integrity_matrix(
        corpus_path,
        profile_path,
        matrix_path,
        20260827,
        output,
        evaluation,
        command=command,
    )

    assert first == second
    assert (output / "summary.json").read_bytes() == first_json
    assert evaluation.read_bytes() == first_markdown
    assert first["status"] == "complete"
    assert first["scheduled_tamper_cases"] == 1
    assert first["aggregate_iou_denominator"] == 1
    assert first["failed_cases"] == 0
    assert first["limited_cases"] == 0
    assert first["aggregate_iou"] >= 0.50
    assert first["per_tamper"][0]["tamper_kind"] == "cover_region"
    assert first["per_tamper"][0]["scheduled_cases"] == 1
    assert first["corpus_sha256"] == hashlib.sha256(corpus_path.read_bytes()).hexdigest()
    assert first["profile_sha256"] == hashlib.sha256(profile_path.read_bytes()).hexdigest()
    assert first["matrix_sha256"] == hashlib.sha256(matrix_path.read_bytes()).hexdigest()
    assert first["seed"] == 20260827
    assert first["command"] == command
    serialized = json.dumps(first, sort_keys=True)
    assert "fingerprint" not in serialized.lower()
    assert "private" not in serialized.lower()
    assert command in evaluation.read_text(encoding="utf-8")
