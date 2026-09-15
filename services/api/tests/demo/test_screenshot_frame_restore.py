import uuid

import cv2
import numpy as np
import pytest

from splitbind.demo.issuance import _canonicalize_page, _select_frozen_candidate
from splitbind.demo.models import DEMO_CANONICAL_CANVAS
from splitbind.demo.verification import PAGE_INDEX_HYPOTHESES, _decode_image
from splitbind_ref.fingerprint_v2 import (
    FingerprintV2Context,
    decode_fingerprint_v2,
    embed_fingerprint_v2,
)
from splitbind_ref.frame_restore import restore_frame


KEY = bytes.fromhex("00112233445566778899aabbccddeeff" * 2)
ISSUANCE_ID = uuid.UUID("12345678-1234-5678-1234-567812345678")
SCREEN = (1080, 1920)


def _gradient_page() -> np.ndarray:
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


def _letterbox(page: np.ndarray) -> np.ndarray:
    screen_height, screen_width = SCREEN
    page_height, page_width = page.shape[:2]
    scale = min(screen_width / page_width, screen_height / page_height)
    fitted = cv2.resize(
        page,
        (round(page_width * scale), round(page_height * scale)),
        interpolation=cv2.INTER_AREA,
    )
    screen = np.zeros((screen_height, screen_width, 3), dtype=np.uint8)
    top = (screen_height - fitted.shape[0]) // 2
    left = (screen_width - fitted.shape[1]) // 2
    screen[top : top + fitted.shape[0], left : left + fitted.shape[1]] = fitted
    return screen


@pytest.fixture(scope="module")
def screenshot_png() -> bytes:
    candidate, _identifier = _select_frozen_candidate()
    marked = embed_fingerprint_v2(
        _gradient_page(),
        FingerprintV2Context(ISSUANCE_ID, KEY, 0),
        candidate,
    )
    page = marked.image if hasattr(marked, "image") else marked
    ok, encoded = cv2.imencode(".png", _letterbox(np.asarray(page, dtype=np.uint8)))
    assert ok
    return encoded.tobytes()


def test_frame_restoration_makes_the_letterboxed_page_decodable(screenshot_png):
    candidate, _identifier = _select_frozen_candidate()
    raster = cv2.imdecode(np.frombuffer(screenshot_png, dtype=np.uint8), cv2.IMREAD_COLOR)

    restored = restore_frame(raster, DEMO_CANONICAL_CANVAS)

    assert restored is not None
    assert restored.trimmed
    decision = decode_fingerprint_v2(
        np.ascontiguousarray(restored.image),
        KEY,
        0,
        DEMO_CANONICAL_CANVAS,
        (candidate,),
    )
    assert decision.status == "decoded"
    assert decision.issuance_id == ISSUANCE_ID


def test_plain_canonicalization_cannot_read_the_letterboxed_page(screenshot_png):
    candidate, _identifier = _select_frozen_candidate()
    raster = cv2.imdecode(np.frombuffer(screenshot_png, dtype=np.uint8), cv2.IMREAD_COLOR)

    decision = decode_fingerprint_v2(
        np.ascontiguousarray(_canonicalize_page(raster).canvas),
        KEY,
        0,
        DEMO_CANONICAL_CANVAS,
        (candidate,),
    )

    assert decision.status == "insufficient_sync_evidence"


def test_only_the_embedded_page_index_ever_decodes(screenshot_png):
    candidate, _identifier = _select_frozen_candidate()
    raster = cv2.imdecode(np.frombuffer(screenshot_png, dtype=np.uint8), cv2.IMREAD_COLOR)
    restored = restore_frame(raster, DEMO_CANONICAL_CANVAS)

    decoded = [
        page_index
        for page_index in range(PAGE_INDEX_HYPOTHESES)
        if decode_fingerprint_v2(
            np.ascontiguousarray(restored.image),
            KEY,
            page_index,
            DEMO_CANONICAL_CANVAS,
            (candidate,),
        ).status
        == "decoded"
    ]

    assert decoded == [0]


def test_letterboxed_screenshot_is_attributed(screenshot_png):
    candidate, _identifier = _select_frozen_candidate()
    height, width = SCREEN

    summary, pages = _decode_image(
        screenshot_png,
        width=width,
        height=height,
        fingerprint_key=KEY,
        candidates=(candidate,),
    )

    assert pages == 1
    assert summary.status == "decoded", summary.status
    assert summary.issuance_id == ISSUANCE_ID
