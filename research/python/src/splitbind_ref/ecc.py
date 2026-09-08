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


def decode_ecc_with_erasures(
    codeword: bytes,
    erase_positions: tuple[int, ...],
    parity_symbols: int = 16,
) -> bytes:
    """Decode an interleaved codeword using interleaved byte erasure positions.

    The Reed-Solomon library receives positions in its raw (pre-interleave)
    coordinate system.  Callers remain in the public, interleaved 39-byte
    coordinate system used by :func:`encode_ecc` and V2 extraction.
    """

    profile = payload_profile()
    message_bytes = profile["reed_solomon"]["message_bytes"]
    contracted_parity = profile["reed_solomon"]["parity_symbols"]
    _validate_parity_symbols(parity_symbols, contracted_parity)
    expected_length = message_bytes + parity_symbols
    if len(codeword) != expected_length:
        raise ValueError(f"Reed-Solomon codeword must be {expected_length} bytes")
    positions = _validate_erase_positions(erase_positions, expected_length)
    if len(positions) > parity_symbols:
        raise EccDecodeError("Reed-Solomon erasures exceed correction capacity")

    depth = profile["interleave_depth"]
    raw_codeword = deinterleave(codeword, depth)
    raw_index_at_interleaved_position = interleave(bytes(range(expected_length)), depth)
    raw_erase_positions = [raw_index_at_interleaved_position[position] for position in positions]
    try:
        decoded, _, _ = _codec(parity_symbols).decode(
            raw_codeword, erase_pos=raw_erase_positions
        )
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


def _validate_erase_positions(
    erase_positions: tuple[int, ...], expected_length: int
) -> tuple[int, ...]:
    if not isinstance(erase_positions, tuple):
        raise TypeError("erase_positions must be a tuple of byte indices")
    if any(
        not isinstance(position, int)
        or isinstance(position, bool)
        or not 0 <= position < expected_length
        for position in erase_positions
    ):
        raise ValueError("erase_positions must be valid codeword byte indices")
    if len(set(erase_positions)) != len(erase_positions):
        raise ValueError("erase_positions must not contain duplicates")
    return erase_positions
