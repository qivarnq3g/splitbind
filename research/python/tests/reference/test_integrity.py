import copy
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from splitbind_attack.attacks import AttackCase, apply_attack
from splitbind_bench.metrics import compute_localization_iou
from splitbind_ref.integrity import embed_integrity, verify_integrity


ROOT = Path(__file__).resolve().parents[4]
PROFILE_PATH = ROOT / "contracts/algorithm/integrity-profile.v1.json"


@pytest.fixture
def profile():
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def page():
    y, x = np.indices((512, 512), dtype=np.uint16)
    image = np.empty((512, 512, 3), dtype=np.uint8)
    image[..., 0] = (x * 3 + y * 5) % 256
    image[..., 1] = (x * 7 + y * 2 + ((x // 32) % 2) * 40) % 256
    image[..., 2] = (x + y * 11 + ((y // 24) % 2) * 50) % 256
    return image


@pytest.fixture
def integrity_context(profile):
    return {"key": b"integrity-test-key-material-32b!", "nonce": b"document-nonce-v1", "profile": profile}


def test_clean_roundtrip_is_deterministic_and_does_not_mutate_input(
    page, integrity_context
):
    before = page.copy()

    first = embed_integrity(page, **integrity_context)
    second = embed_integrity(page, **integrity_context)
    decision = verify_integrity(first.image, **integrity_context)

    assert np.array_equal(page, before)
    assert not np.shares_memory(first.image, page)
    assert np.array_equal(first.image, second.image)
    assert decision.score == 1.0
    assert decision.suspicious_regions == ()
    assert decision.evaluated_regions == 16
    assert decision.limitations == ()


def test_aligned_content_tamper_marks_the_ground_truth_region(
    page, integrity_context
):
    embedded = embed_integrity(page, **integrity_context)
    attack = AttackCase(
        "aligned-cover",
        "tamper",
        {
            "kind": "cover_region",
            "region": {"x": 0.25, "y": 0.25, "width": 0.25, "height": 0.25},
        },
    )
    artifact = apply_attack(embedded.image, attack, np.random.default_rng(20260827))

    decision = verify_integrity(artifact.image, **integrity_context)

    assert compute_localization_iou(
        artifact.ground_truth, decision.suspicious_regions
    ) >= 0.50


def test_benign_jpeg_95_does_not_create_suspicious_regions(page, integrity_context):
    embedded = embed_integrity(page, **integrity_context)
    encoded, buffer = cv2.imencode(
        ".jpg", embedded.image, [cv2.IMWRITE_JPEG_QUALITY, 95]
    )
    assert encoded
    transformed = cv2.imdecode(buffer, cv2.IMREAD_COLOR)

    decision = verify_integrity(transformed, **integrity_context)

    assert decision.suspicious_regions == ()
    assert decision.score == 1.0


def test_small_page_returns_stable_insufficient_regions_limitation(profile):
    page = np.zeros((127, 512, 3), dtype=np.uint8)

    embedded = embed_integrity(
        page, b"integrity-test-key", b"document-nonce", profile
    )
    decision = verify_integrity(
        embedded.image, b"integrity-test-key", b"document-nonce", profile
    )

    assert np.array_equal(embedded.image, page)
    assert decision.evaluated_regions == 0
    assert decision.suspicious_regions == ()
    assert decision.limitations == ("integrity.insufficient_complete_regions",)


def test_geometry_change_is_indeterminate_not_a_content_tamper(page, integrity_context):
    embedded = embed_integrity(page, **integrity_context)
    cropped = embedded.image[:384].copy()

    decision = verify_integrity(cropped, **integrity_context)

    assert "integrity.geometry_failure" in decision.limitations
    assert decision.suspicious_regions == ()


def test_strong_compression_reports_a_stable_limitation(page, integrity_context):
    embedded = embed_integrity(page, **integrity_context)
    encoded, buffer = cv2.imencode(
        ".jpg", embedded.image, [cv2.IMWRITE_JPEG_QUALITY, 35]
    )
    assert encoded
    compressed = cv2.imdecode(buffer, cv2.IMREAD_COLOR)

    decision = verify_integrity(compressed, **integrity_context)

    assert "integrity.strong_compression" in decision.limitations


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update(status="released-without-measurement"),
        lambda value: value.update(region_size_px=64),
        lambda value: value["content_feature"].update(transform="fft"),
        lambda value: value["content_feature"].update(quantization_step=float("nan")),
        lambda value: value["embedding"].update(tag_coefficient_sets=[[1, 1]]),
        lambda value: value.update(unrecognized_material_choice=True),
    ],
)
def test_profile_validation_fails_closed(page, profile, mutate):
    invalid = copy.deepcopy(profile)
    mutate(invalid)

    with pytest.raises((TypeError, ValueError), match="integrity profile"):
        embed_integrity(page, b"integrity-test-key", b"document-nonce", invalid)


@pytest.mark.parametrize(
    ("page", "key", "nonce", "error"),
    [
        (np.zeros((128, 128, 3), dtype=np.float32), b"k" * 16, b"n" * 8, "uint8"),
        (np.zeros((128, 128, 4), dtype=np.uint8), b"k" * 16, b"n" * 8, "channel"),
        (np.zeros((0, 128, 3), dtype=np.uint8), b"k" * 16, b"n" * 8, "non-empty"),
        (np.zeros((6325, 6325), dtype=np.uint8), b"k" * 16, b"n" * 8, "40 megapixels"),
        (np.zeros((128, 128), dtype=np.uint8), b"", b"n" * 8, "key"),
        (np.zeros((128, 128), dtype=np.uint8), b"k" * 65, b"n" * 8, "key"),
        (np.zeros((128, 128), dtype=np.uint8), b"k" * 16, b"", "nonce"),
        (np.zeros((128, 128), dtype=np.uint8), b"k" * 16, b"n" * 65, "nonce"),
    ],
)
def test_input_bounds_are_enforced(page, key, nonce, error, profile):
    with pytest.raises((TypeError, ValueError), match=error):
        embed_integrity(page, key, nonce, profile)
