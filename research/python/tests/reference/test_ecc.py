import pytest
from hypothesis import given
from hypothesis import strategies as st

from splitbind_ref.ecc import (
    EccDecodeError,
    decode_ecc,
    decode_ecc_with_erasures,
    deinterleave,
    encode_ecc,
    interleave,
)


def test_interleave_has_a_hand_derived_depth_eight_order():
    assert interleave(b"0123456789", depth=8) == b"0819234567"


@given(st.binary(max_size=255), st.integers(min_value=1, max_value=32))
def test_interleave_is_invertible_for_ragged_rows(value, depth):
    assert deinterleave(interleave(value, depth), depth) == value


@given(st.binary(min_size=23, max_size=23), st.integers(min_value=0, max_value=8))
def test_shortened_rs_corrects_up_to_eight_symbol_errors(payload, count):
    codeword = bytearray(encode_ecc(payload, parity_symbols=16))
    for index in range(count):
        codeword[index] ^= 0x5A

    assert len(codeword) == 39
    assert decode_ecc(bytes(codeword), parity_symbols=16) == payload


def test_shortened_rs_rejects_nine_symbol_errors():
    payload = bytes.fromhex("534201123456781234567812345678123456789ae24281")
    codeword = bytearray(encode_ecc(payload, parity_symbols=16))
    for index in range(9):
        codeword[index] ^= index + 1

    with pytest.raises(EccDecodeError):
        decode_ecc(bytes(codeword), parity_symbols=16)


@pytest.mark.parametrize("length", [22, 24])
def test_shortened_rs_rejects_non_contract_payload_lengths(length):
    with pytest.raises(ValueError, match="23"):
        encode_ecc(bytes(length), parity_symbols=16)


def test_shortened_rs_rejects_wrong_codeword_length():
    with pytest.raises(ValueError, match="39"):
        decode_ecc(bytes(38), parity_symbols=16)


def test_shortened_rs_rejects_parity_outside_the_frozen_contract():
    with pytest.raises(ValueError, match="16"):
        encode_ecc(bytes(23), parity_symbols=15)


def test_rs_v2_uses_bounded_byte_erasures():
    payload = bytes.fromhex("534201123456781234567812345678123456789ae24281")
    codeword = bytearray(encode_ecc(payload))
    for index in range(16):
        codeword[index] = 0

    assert decode_ecc_with_erasures(bytes(codeword), tuple(range(16))) == payload


def test_rs_v2_rejects_seventeen_byte_erasures():
    payload = bytes.fromhex("534201123456781234567812345678123456789ae24281")
    codeword = bytearray(encode_ecc(payload))
    for index in range(17):
        codeword[index] = 0

    with pytest.raises(EccDecodeError):
        decode_ecc_with_erasures(bytes(codeword), tuple(range(17)))


def test_v1_decode_ecc_still_rejects_the_same_uncorrectable_error_pattern():
    payload = bytes.fromhex("534201123456781234567812345678123456789ae24281")
    codeword = bytearray(encode_ecc(payload))
    for index in range(9):
        codeword[index] ^= index + 1

    with pytest.raises(EccDecodeError):
        decode_ecc(bytes(codeword))
