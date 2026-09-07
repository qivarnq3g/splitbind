from uuid import UUID

import numpy as np

from splitbind.release.marker import apply_visible_marker, marker_text


def test_marker_is_stable_and_contains_no_personal_data():
    value = marker_text(UUID("00112233-4455-6677-8899-aabbccddeeff"))

    assert value == "SB1-AAISEM2EKVTHPCEZVK54"


def test_visible_marker_is_deterministic_and_does_not_mutate_input():
    source = np.full((480, 640, 3), 127, dtype=np.uint8)
    original = source.copy()
    issuance_id = UUID("00112233-4455-6677-8899-aabbccddeeff")

    first = apply_visible_marker(source, issuance_id)
    second = apply_visible_marker(source, issuance_id)

    assert np.array_equal(source, original)
    assert np.array_equal(first, second)
    assert not np.array_equal(first, source)
    assert np.array_equal(first[:360], source[:360])
