from uuid import UUID

import pytest

from splitbind_ref.payload import PayloadDecode, decode_payload, encode_payload, verify_crc


ISSUANCE_ID = UUID("12345678-1234-5678-1234-567812345678")
GOLDEN_PAYLOAD = bytes.fromhex(
    "534201123456781234567812345678123456789ae24281"
)


def test_payload_has_stable_network_byte_order():
    value = encode_payload(ISSUANCE_ID, 1)

    assert value[:19].hex() == "53420112345678123456781234567812345678"
    assert value == GOLDEN_PAYLOAD
    assert len(value) == 23


def test_decode_payload_recovers_version_and_issuance_identifier():
    assert decode_payload(GOLDEN_PAYLOAD) == PayloadDecode(
        issuance_id=ISSUANCE_ID,
        version=1,
    )


def test_crc_rejects_a_corrupted_payload():
    corrupted = bytearray(GOLDEN_PAYLOAD)
    corrupted[8] ^= 0x01

    assert verify_crc(GOLDEN_PAYLOAD) is True
    assert verify_crc(bytes(corrupted)) is False
    with pytest.raises(ValueError, match="CRC"):
        decode_payload(bytes(corrupted))


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (GOLDEN_PAYLOAD[:-1], "length"),
        (b"XX" + GOLDEN_PAYLOAD[2:], "magic"),
        (GOLDEN_PAYLOAD[:2] + b"\x02" + GOLDEN_PAYLOAD[3:], "version"),
    ],
)
def test_decode_payload_rejects_values_outside_the_frozen_contract(value, message):
    with pytest.raises(ValueError, match=message):
        decode_payload(value)


def test_encode_payload_rejects_an_unsupported_version():
    with pytest.raises(ValueError, match="version"):
        encode_payload(ISSUANCE_ID, version=2)
