"""V3 position binding and independent LL-DCT payload round trips."""

import math
from dataclasses import replace
from uuid import UUID

import numpy as np
import pytest

from splitbind_ref.ecc import EccDecodeError, decode_ecc_with_erasures, encode_ecc
from splitbind_ref.fingerprint_v2_codec import _selected_positions as v2_positions
from splitbind_ref.fingerprint_v3_dct import (
    _selected_positions, embed_codeword_v3, extract_codeword_v3,
)
from splitbind_ref.fingerprint_v3_profile import load_v3_profiles, v2_pilot_profile
from splitbind_ref.payload import decode_payload, encode_payload
from splitbind_ref.tile_layout_v2 import derive_tiles_v2
from splitbind_ref.tile_layout_v3 import derive_tiles_v3

KEY = bytes.fromhex("00112233445566778899aabbccddeeff" * 2)
ISSUANCE_ID = UUID("12345678-1234-5678-1234-567812345678")


@pytest.mark.parametrize("profile", load_v3_profiles())
def test_v3_dct_roundtrip_is_bound_and_does_not_mutate(profile):
    tile = np.random.default_rng(20260905).uniform(50, 200, (profile.tile_size_px,) * 2)
    before = tile.copy()
    codeword = encode_ecc(encode_payload(ISSUANCE_ID))
    encoded = embed_codeword_v3(tile, codeword, KEY, 0, profile)
    evidence = extract_codeword_v3(encoded, KEY, 0, profile)
    assert evidence.codeword == codeword
    assert evidence.erase_positions == ()
    np.testing.assert_array_equal(tile, before)
    assert not np.shares_memory(encoded, tile)
    assert _selected_positions(KEY, 0, profile) != v2_positions(KEY, 0, v2_pilot_profile(profile))
    wrong = replace(profile, spread_delta=profile.spread_delta + 1)
    evidence = extract_codeword_v3(encoded, KEY, 0, wrong)
    with pytest.raises((EccDecodeError, ValueError)):
        decode_payload(decode_ecc_with_erasures(evidence.codeword, evidence.erase_positions))


def test_v3_layout_is_nonoverlapping_and_bound_to_entire_candidate():
    profile = load_v3_profiles()[0]
    tiles = derive_tiles_v3((1536, 3072), KEY, 0, profile)
    assert tiles == derive_tiles_v3((1536, 3072), KEY, 0, profile)
    assert len(tiles) == len(set(tiles)) == 18
    for i, first in enumerate(tiles):
        assert 0 <= first.x <= 3072 - first.width
        assert 0 <= first.y <= 1536 - first.height
        for second in tiles[i + 1:]:
            assert (first.x + first.width <= second.x or second.x + second.width <= first.x
                    or first.y + first.height <= second.y or second.y + second.height <= first.y)
    assert tiles != derive_tiles_v2((1536, 3072), KEY, 0, v2_pilot_profile(profile))
    assert tiles != derive_tiles_v3((1536, 3072), KEY, 1, profile)
    assert tiles != derive_tiles_v3((1536, 3072), b"wrong", 0, profile)
    assert tiles != derive_tiles_v3((1536, 3072), KEY, 0, replace(profile, spread_delta=5.0))


def test_v3_layout_refuses_insufficient_capacity():
    with pytest.raises(ValueError, match="non-overlapping"):
        derive_tiles_v3((384, 384), KEY, 0, load_v3_profiles()[0])


@pytest.mark.parametrize("profile", load_v3_profiles())
def test_v3_payload_layout_keeps_crop_quorum_inside_frozen_retained_scale(profile):
    """Catches shuffled payload tiles that lose quorum under the frozen center crop."""

    height, width = 1536, 3072
    retained_scale = min(profile.crop_retained_scales)
    retained_height = round(height * retained_scale)
    retained_width = round(width * retained_scale)
    y0 = (height - retained_height) // 2
    x0 = (width - retained_width) // 2
    payload_tiles = derive_tiles_v3((height, width), KEY, 0, profile)[
        : profile.payload_repetitions
    ]
    surviving = sum(
        x0 <= tile.x
        and y0 <= tile.y
        and tile.x + tile.width <= x0 + retained_width
        and tile.y + tile.height <= y0 + retained_height
        for tile in payload_tiles
    )

    assert surviving >= max(2, math.ceil(0.60 * profile.payload_repetitions))
