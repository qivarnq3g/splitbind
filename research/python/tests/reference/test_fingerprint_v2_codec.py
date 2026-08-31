from uuid import UUID

import cv2
import numpy as np
import pytest

from splitbind_ref.dwt_dct_qim import haar_idwt2, idct2
from splitbind_ref.ecc import EccDecodeError, decode_ecc_with_erasures, encode_ecc
from splitbind_ref.fingerprint_v2_codec import (
    _capacity,
    _selected_positions,
    embed_codeword_v2,
    extract_codeword_v2,
)
from splitbind_ref.fingerprint_v2_profile import load_v2_profiles
from splitbind_ref.payload import decode_payload, encode_payload


KEY = bytes.fromhex("00112233445566778899aabbccddeeff" * 2)


@pytest.fixture
def profile():
    return load_v2_profiles()[0]


@pytest.fixture
def codeword():
    return encode_ecc(encode_payload(UUID("12345678-1234-5678-1234-567812345678")))


@pytest.fixture
def sample_tile(profile):
    rows, columns = np.indices((profile.tile_size_px, profile.tile_size_px))
    return (96.0 + (rows * 7 + columns * 13) % 127).astype(np.float64)


def test_clean_ll_codec_recovers_all_bits(profile, sample_tile, codeword):
    encoded = embed_codeword_v2(sample_tile, codeword, KEY, 0, profile)
    evidence = extract_codeword_v2(encoded, KEY, 0, profile)

    assert evidence.codeword == codeword
    assert evidence.erase_positions == ()
    assert evidence.mean_confidence == pytest.approx(1.0)
    assert evidence.bit_error_hint == pytest.approx(0.0)


def test_v2_codec_never_mutates_its_input_array(profile, sample_tile, codeword):
    original = sample_tile.copy()

    encoded = embed_codeword_v2(sample_tile, codeword, KEY, 0, profile)
    encoded_before_extraction = encoded.copy()
    extract_codeword_v2(encoded, KEY, 0, profile)

    np.testing.assert_array_equal(sample_tile, original)
    np.testing.assert_array_equal(encoded, encoded_before_extraction)
    assert not np.shares_memory(encoded, sample_tile)


def test_v2_codec_selects_unique_dct_positions_inside_each_profiles_capacity():
    for profile in load_v2_profiles():
        positions = _selected_positions(KEY, 0, profile)

        assert len(positions) == 39 * 8 * profile.bit_replication
        assert len(set(positions)) == len(positions)
        assert all(0 <= position < _capacity(profile) for position in positions)


def test_v2_codec_places_each_bits_replicas_in_distinct_dct_blocks(profile):
    positions = _selected_positions(bytes([1]) * 32, 1, profile)

    for bit_index in range(39 * 8):
        start = bit_index * profile.bit_replication
        replica_blocks = {
            position // 2
            for position in positions[start : start + profile.bit_replication]
        }
        assert len(replica_blocks) == profile.bit_replication


def test_v2_codec_marks_every_byte_with_low_confidence_bits_as_an_erasure(profile):
    ll_edge = profile.tile_size_px // 2
    ll = np.empty((ll_edge, ll_edge), dtype=np.float64)
    difference = 0.49 * profile.qim_delta
    coefficient_pairs = (((1, 2), (2, 1)), ((2, 3), (3, 2)))
    for y in range(0, ll_edge, 8):
        for x in range(0, ll_edge, 8):
            coefficients = np.zeros((8, 8), dtype=np.float64)
            for first, second in coefficient_pairs:
                coefficients[first] = difference / 2.0
                coefficients[second] = -difference / 2.0
            ll[y : y + 8, x : x + 8] = idct2(coefficients)
    zero_band = np.zeros_like(ll)
    tile = haar_idwt2(
        ll,
        zero_band,
        zero_band,
        zero_band,
        (profile.tile_size_px, profile.tile_size_px),
    )

    evidence = extract_codeword_v2(tile, KEY, 0, profile)

    assert evidence.erase_positions == tuple(range(39))
    assert evidence.mean_confidence == pytest.approx(0.02, abs=1e-12)


@pytest.mark.parametrize(
    ("key", "page_index", "profile_index"),
    [(b"w" * 32, 0, 0), (KEY, 1, 0), (KEY, 0, 1)],
)
def test_wrong_v2_binding_cannot_produce_a_crc_valid_payload(
    profile, sample_tile, codeword, key, page_index, profile_index
):
    encoded = embed_codeword_v2(sample_tile, codeword, KEY, 0, profile)
    wrong_profile = load_v2_profiles()[profile_index]
    evidence = extract_codeword_v2(encoded, key, page_index, wrong_profile)

    with pytest.raises((EccDecodeError, ValueError)):
        decode_payload(
            decode_ecc_with_erasures(evidence.codeword, evidence.erase_positions)
        )


def test_jpeg_70_component_probe_reports_measured_evidence(profile, sample_tile, codeword):
    encoded = embed_codeword_v2(sample_tile, codeword, KEY, 0, profile)
    compressed_ok, compressed = cv2.imencode(
        ".jpg", np.clip(encoded, 0, 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 70]
    )

    assert compressed_ok
    recovered = cv2.imdecode(compressed, cv2.IMREAD_GRAYSCALE).astype(np.float64)
    evidence = extract_codeword_v2(recovered, KEY, 0, profile)
    expected_bits = np.unpackbits(np.frombuffer(codeword, dtype=np.uint8), bitorder="big")
    observed_bits = np.unpackbits(np.frombuffer(evidence.codeword, dtype=np.uint8), bitorder="big")
    measured_ber = float(
        np.count_nonzero(expected_bits != observed_bits) / expected_bits.size
    )

    assert measured_ber < 0.10
    assert 0.50 <= evidence.mean_confidence <= 1.0
    assert evidence.bit_error_hint is not None
    assert 0.0 <= evidence.bit_error_hint < 0.15
