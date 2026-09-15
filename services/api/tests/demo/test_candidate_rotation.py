import uuid

import cv2
import numpy as np
import pytest

from splitbind.demo.issuance import (
    _candidate_by_identifier,
    _select_frozen_candidate,
    accepted_decode_candidates,
)
from splitbind.demo.models import (
    DEMO_ACCEPTED_CANDIDATE_IDENTIFIERS,
    DEMO_CANONICAL_CANVAS,
    DEMO_FROZEN_CANDIDATE_IDENTIFIER,
    DEMO_LEGACY_CANDIDATE_IDENTIFIERS,
)
from splitbind.demo.verification import _decode_image
from splitbind_ref.fingerprint_v2 import FingerprintV2Context, embed_fingerprint_v2
from splitbind_ref.fingerprint_v2_profile import candidate_identifier_v2


KEY = bytes.fromhex("00112233445566778899aabbccddeeff" * 2)
ISSUANCE_ID = uuid.UUID("12345678-1234-5678-1234-567812345678")


def text_page() -> np.ndarray:
    height, width = DEMO_CANONICAL_CANVAS
    page = np.full((height, width, 3), 252, dtype=np.uint8)
    rng = np.random.default_rng(9)
    y = int(height * 0.08)
    line_height = max(18, height // 66)
    while y < height - line_height * 2:
        x = int(width * 0.08)
        limit = int(width * 0.92)
        while x < limit:
            word = int(rng.integers(int(width * 0.03), int(width * 0.11)))
            cv2.rectangle(
                page,
                (x, y),
                (min(x + word, limit), y + max(6, line_height // 3)),
                (40, 40, 44),
                -1,
            )
            x += word + max(6, line_height // 3)
        y += line_height
    return page


def gradient_page() -> np.ndarray:
    height, width = DEMO_CANONICAL_CANVAS
    y, x = np.indices((height, width), dtype=np.float64)
    return (
        np.stack(
            (
                30.0 + 148.0 * x / (width - 1) + 16.0 * y / (height - 1),
                39.0 + 131.0 * x / (width - 1) + 21.0 * y / (height - 1),
                47.0 + 117.0 * x / (width - 1) + 27.0 * y / (height - 1),
            ),
            axis=2,
        )
        .clip(0, 255)
        .astype(np.uint8)
    )


def encode_png(page: np.ndarray) -> bytes:
    written, encoded = cv2.imencode(".png", page)
    assert written
    return encoded.tobytes()


def attribute(page: np.ndarray):
    height, width = page.shape[:2]
    summary, pages = _decode_image(
        encode_png(page),
        width=width,
        height=height,
        fingerprint_key=KEY,
        candidates=accepted_decode_candidates(),
    )
    assert pages == 1
    return summary


def embedded_with(identifier: str, page: np.ndarray) -> np.ndarray:
    candidate, _identifier = _candidate_by_identifier(identifier)
    marked = embed_fingerprint_v2(
        page,
        FingerprintV2Context(ISSUANCE_ID, KEY, 0),
        candidate,
    )
    return np.ascontiguousarray(marked.image, dtype=np.uint8)


def test_the_frozen_profile_is_the_one_the_contract_names():
    candidate, identifier = _select_frozen_candidate()
    assert identifier == DEMO_FROZEN_CANDIDATE_IDENTIFIER
    assert candidate_identifier_v2(candidate).hex() == DEMO_FROZEN_CANDIDATE_IDENTIFIER


def test_the_frozen_profile_is_tried_before_any_superseded_one():
    identifiers = [
        candidate_identifier_v2(candidate).hex()
        for candidate in accepted_decode_candidates()
    ]
    assert identifiers == list(DEMO_ACCEPTED_CANDIDATE_IDENTIFIERS)
    assert identifiers[0] == DEMO_FROZEN_CANDIDATE_IDENTIFIER


def test_a_text_page_issued_with_the_frozen_profile_is_attributed():
    """The reason the frozen profile moved: the superseded one never synchronised here."""

    summary = attribute(embedded_with(DEMO_FROZEN_CANDIDATE_IDENTIFIER, text_page()))
    assert summary.status == "decoded", summary.status
    assert summary.issuance_id == ISSUANCE_ID


def test_the_superseded_profile_still_cannot_read_a_text_page():
    for identifier in DEMO_LEGACY_CANDIDATE_IDENTIFIERS:
        summary = attribute(embedded_with(identifier, text_page()))
        assert summary.status == "insufficient_sync_evidence", summary.status


@pytest.mark.parametrize("identifier", DEMO_LEGACY_CANDIDATE_IDENTIFIERS)
def test_an_artifact_issued_before_the_change_still_resolves(identifier):
    """Backward compatibility, measured on a carrier the superseded profile could read."""

    summary = attribute(embedded_with(identifier, gradient_page()))
    assert summary.status == "decoded", summary.status
    assert summary.issuance_id == ISSUANCE_ID


def test_the_frozen_profile_also_reads_the_carrier_the_old_one_handled():
    summary = attribute(embedded_with(DEMO_FROZEN_CANDIDATE_IDENTIFIER, gradient_page()))
    assert summary.status == "decoded", summary.status
    assert summary.issuance_id == ISSUANCE_ID
