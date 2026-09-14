import cv2
import numpy as np

from splitbind_ref.frame_restore import content_bounds, restore_frame


CANONICAL = (192, 384)


def page(height: int, width: int, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.integers(40, 216, size=(height, width), dtype=np.uint8)


def letterbox(content: np.ndarray, top: int, left: int, border: int = 0) -> np.ndarray:
    height, width = content.shape[:2]
    canvas = np.full((height + 2 * top, width + 2 * left), border, dtype=np.uint8)
    canvas[top : top + height, left : left + width] = content
    return canvas


def test_bounds_find_the_page_inside_a_letterbox():
    content = page(60, 120)
    framed = letterbox(content, 20, 35)

    top, left, height, width = content_bounds(framed)

    assert (top, left, height, width) == (20, 35, 60, 120)


def test_bounds_leave_a_page_without_a_border_untouched():
    content = page(60, 120)

    assert content_bounds(content) == (0, 0, 60, 120)


def test_bounds_refuse_to_trim_away_almost_everything():
    canvas = np.zeros((200, 400), dtype=np.uint8)
    canvas[100:102, 200:202] = 255

    assert content_bounds(canvas) == (0, 0, 200, 400)


def test_restoring_a_letterboxed_page_recovers_the_canonical_canvas():
    content = page(*CANONICAL)
    framed = letterbox(content, 40, 90)

    restored = restore_frame(framed, CANONICAL)

    assert restored is not None
    assert restored.trimmed is True
    assert restored.image.shape[:2] == CANONICAL
    assert float(np.mean(np.abs(restored.image.astype(np.int16) - content.astype(np.int16)))) < 1.0


def test_restoring_maps_a_content_corner_onto_the_canonical_corner():
    content = page(*CANONICAL)
    framed = letterbox(content, 40, 90)

    restored = restore_frame(framed, CANONICAL)

    assert restored is not None
    origin = restored.source_to_canonical @ np.array([90.0, 40.0, 1.0])
    assert abs(origin[0]) < 1.0
    assert abs(origin[1]) < 1.0


def test_restoring_rescales_a_shrunken_page_back_to_canonical():
    content = page(*CANONICAL)
    shrunk = cv2.resize(content, (CANONICAL[1] // 2, CANONICAL[0] // 2), interpolation=cv2.INTER_AREA)

    restored = restore_frame(shrunk, CANONICAL)

    assert restored is not None
    assert restored.image.shape[:2] == CANONICAL


def test_restoring_declines_a_page_already_at_canonical_size():
    assert restore_frame(page(*CANONICAL), CANONICAL) is None
