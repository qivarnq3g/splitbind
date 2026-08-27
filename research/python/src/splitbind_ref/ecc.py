"""Shortened Reed-Solomon framing and deterministic byte interleaving."""

from __future__ import annotations

from reedsolo import RSCodec, ReedSolomonError

from .contracts import payload_profile


class EccDecodeError(ValueError):
    """Raised when a Reed-Solomon codeword cannot be decoded safely."""


def interleave(data: bytes, depth: int) -> bytes:
    """Spread adjacent bytes across ``depth`` lanes."""

    if depth <= 0:
        raise ValueError("interleave depth must be positive")
    return b"".join(data[offset::depth] for offset in range(depth))


def deinterleave(data: bytes, depth: int) -> bytes:
    """Invert :func:`interleave`, including when the final row is ragged."""

    if depth <= 0:
        raise ValueError("interleave depth must be positive")

    restored = bytearray(len(data))
    cursor = 0
    for offset in range(depth):
        lane_length = len(range(offset, len(data), depth))
        restored[offset::depth] = data[cursor : cursor + lane_length]
        cursor += lane_length
    return bytes(restored)


def encode_ecc(payload: bytes, parity_symbols: int = 16) -> bytes:
    profile = payload_profile()
    message_bytes = profile["reed_solomon"]["message_bytes"]
    contracted_parity = profile["reed_solomon"]["parity_symbols"]
    if len(payload) != message_bytes:
        raise ValueError(f"Reed-Solomon payload must be {message_bytes} bytes")
    _validate_parity_symbols(parity_symbols, contracted_parity)

    codec = _codec(parity_symbols)
    codeword = bytes(codec.encode(payload))
    return interleave(codeword, profile["interleave_depth"])


def decode_ecc(codeword: bytes, parity_symbols: int = 16) -> bytes:
    profile = payload_profile()
    message_bytes = profile["reed_solomon"]["message_bytes"]
    contracted_parity = profile["reed_solomon"]["parity_symbols"]
    _validate_parity_symbols(parity_symbols, contracted_parity)
    expected_length = message_bytes + parity_symbols
    if len(codeword) != expected_length:
        raise ValueError(f"Reed-Solomon codeword must be {expected_length} bytes")

    raw_codeword = deinterleave(codeword, profile["interleave_depth"])
    try:
        decoded, _, _ = _codec(parity_symbols).decode(raw_codeword)
    except ReedSolomonError as error:
        raise EccDecodeError("Reed-Solomon codeword exceeds correction capacity") from error
    if len(decoded) != message_bytes:
        raise EccDecodeError("Reed-Solomon decoder returned an invalid payload length")
    return bytes(decoded)


def _codec(parity_symbols: int) -> RSCodec:
    primitive = int(payload_profile()["reed_solomon"]["primitive_polynomial"], 16)
    return RSCodec(parity_symbols, nsize=255, fcr=0, prim=primitive, generator=2, c_exp=8)


def _validate_parity_symbols(parity_symbols: int, contracted_parity: int) -> None:
    if not isinstance(parity_symbols, int) or isinstance(parity_symbols, bool):
        raise TypeError("parity_symbols must be an integer")
    if parity_symbols != contracted_parity:
        raise ValueError(
            f"parity_symbols must be {contracted_parity} for the frozen payload contract"
        )
