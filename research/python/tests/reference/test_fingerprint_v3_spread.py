from uuid import UUID

import cv2
import numpy as np
import pytest

from splitbind_bench.metrics import compute_quality_metrics
from splitbind_ref.ecc import EccDecodeError, decode_ecc_with_erasures, encode_ecc
from splitbind_ref.fingerprint_v3_profile import load_v3_profiles
from splitbind_ref.fingerprint_v3_spread import (
    _chip_groups,
    embed_spread_codeword_v3,
    extract_spread_codeword_v3,
)
from splitbind_ref.payload import decode_payload, encode_payload


KEY = bytes.fromhex("00112233445566778899aabbccddeeff" * 2)


@pytest.fixture
def profile():
    return load_v3_profiles()[0]


@pytest.fixture
def codeword():
    payload = encode_payload(UUID("12345678-1234-5678-1234-567812345678"))
    return encode_ecc(payload)


@pytest.mark.parametrize(("level", "polarity"), [(255.0, "darken"), (0.0, "lighten")])
def test_spread_roundtrip_on_saturated_tile(level, polarity, profile, codeword):
    tile = np.full((profile.tile_size_px, profile.tile_size_px), level, np.float64)

    encoded = embed_spread_codeword_v3(tile, codeword, KEY, 0, profile)
    evidence = extract_spread_codeword_v3(encoded, KEY, 0, profile, polarity)

    assert evidence.codeword == codeword
    assert evidence.erase_positions == ()
    assert evidence.mean_confidence == pytest.approx(1.0)
    assert evidence.polarity == polarity
    assert encoded.min() >= 0.0
    assert encoded.max() <= 255.0


def test_wrong_spread_key_cannot_produce_a_crc_valid_payload(profile, codeword):
    tile = np.full((profile.tile_size_px, profile.tile_size_px), 255.0, np.float64)
    encoded = embed_spread_codeword_v3(tile, codeword, KEY, 0, profile)

    evidence = extract_spread_codeword_v3(encoded, bytes([0xA5]) * 32, 0, profile, "darken")

    with pytest.raises((EccDecodeError, ValueError)):
        decode_payload(
            decode_ecc_with_erasures(evidence.codeword, evidence.erase_positions)
        )


def test_spread_codec_never_mutates_its_input_array(profile, codeword):
    tile = np.full((profile.tile_size_px, profile.tile_size_px), 255.0, np.float64)
    original = tile.copy()

    encoded = embed_spread_codeword_v3(tile, codeword, KEY, 0, profile)
    encoded_before_extraction = encoded.copy()
    extract_spread_codeword_v3(encoded, KEY, 0, profile, "darken")

    np.testing.assert_array_equal(tile, original)
    np.testing.assert_array_equal(encoded, encoded_before_extraction)
    assert not np.shares_memory(encoded, tile)


def test_spread_chip_groups_are_deterministic_unique_and_bound_to_page(profile):
    groups = _chip_groups(KEY, 7, profile)
    repeated = _chip_groups(KEY, 7, profile)
    other_page = _chip_groups(KEY, 8, profile)

    assert groups == repeated
    assert groups != other_page
    assert len(groups) == 39 * 8
    assert all(
        len(group_a) == len(group_b) == profile.spread_chips_per_bit
        for group_a, group_b in groups
    )
    positions = [position for pair in groups for group in pair for position in group]
    assert len(set(positions)) == len(positions)
    assert all(0 <= position < profile.tile_size_px**2 for position in positions)
    for group_a, group_b in groups:
        carrier_blocks_a = {
            (position // profile.tile_size_px // 8, position % profile.tile_size_px // 8)
            for position in group_a
        }
        carrier_blocks_b = {
            (position // profile.tile_size_px // 8, position % profile.tile_size_px // 8)
            for position in group_b
        }
        assert carrier_blocks_a == carrier_blocks_b
        assert len(carrier_blocks_a) == 4


def test_spread_marks_a_byte_with_any_low_confidence_bit_as_an_erasure(
    profile, codeword
):
    tile = np.full((profile.tile_size_px, profile.tile_size_px), 255.0, np.float64)
    encoded = embed_spread_codeword_v3(tile, codeword, KEY, 0, profile)
    first_bit = np.unpackbits(np.frombuffer(codeword, dtype=np.uint8), bitorder="big")[0]
    group_a, group_b = _chip_groups(KEY, 0, profile)[0]
    active = group_b if first_bit else group_a
    encoded.reshape(-1)[list(active)] = 255.0

    evidence = extract_spread_codeword_v3(encoded, KEY, 0, profile, "darken")

    assert evidence.erase_positions == (0,)
    assert evidence.mean_confidence == pytest.approx(311 / 312)


@pytest.mark.parametrize("level", [0.0, 255.0])
def test_spread_embedding_stays_within_its_rms_budget(level, profile, codeword):
    tile = np.full((profile.tile_size_px, profile.tile_size_px), level, np.float64)

    encoded = embed_spread_codeword_v3(tile, codeword, KEY, 0, profile)

    rms = float(np.sqrt(np.mean(np.square(encoded - tile))))
    expected = profile.spread_delta * np.sqrt(
        (39 * 8 * profile.spread_chips_per_bit) / tile.size
    )
    assert rms == pytest.approx(expected)
    assert rms <= profile.spread_delta


def test_white_spread_survives_jpeg70_with_quality_budget(profile, codeword):
    source = np.full((profile.tile_size_px, profile.tile_size_px, 3), 255, np.uint8)
    marked_y = embed_spread_codeword_v3(
        source[..., 0].astype(np.float64), codeword, KEY, 0, profile
    )
    marked = np.repeat(np.clip(marked_y, 0, 255).astype(np.uint8)[..., None], 3, axis=2)
    ok, data = cv2.imencode(".jpg", marked, [cv2.IMWRITE_JPEG_QUALITY, 70])
    recovered = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE).astype(np.float64)

    assert ok
    assert (
        extract_spread_codeword_v3(recovered, KEY, 0, profile, "darken").codeword
        == codeword
    )
    assert compute_quality_metrics(source, marked).psnr_db >= 38.0
