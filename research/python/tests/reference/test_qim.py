import math

import numpy as np
import pytest

from splitbind_ref.dwt_dct_qim import (
    dct2,
    embed_bits_in_band,
    haar_dwt2,
    haar_idwt2,
    qim_embed_pair,
    qim_extract_pair,
)


def test_haar_forward_transform_has_a_hand_derived_golden_vector():
    source = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float64)

    ll, lh, hl, hh, original_shape = haar_dwt2(source)

    assert original_shape == (2, 2)
    np.testing.assert_allclose(ll, [[5.0]], atol=1e-12)
    np.testing.assert_allclose(lh, [[-2.0]], atol=1e-12)
    np.testing.assert_allclose(hl, [[-1.0]], atol=1e-12)
    np.testing.assert_allclose(hh, [[0.0]], atol=1e-12)


def test_haar_inverse_crops_the_documented_edge_padding():
    source = np.arange(15, dtype=np.float64).reshape(3, 5)
    coefficients = haar_dwt2(source)

    restored = haar_idwt2(*coefficients)

    assert restored.shape == source.shape
    np.testing.assert_allclose(restored, source, atol=1e-12)


def test_dct_direction_matches_an_independent_impulse_golden():
    source = np.zeros((8, 8), dtype=np.float64)
    source[0, 1] = 1.0

    transformed = dct2(source)

    assert transformed[0, 0] == pytest.approx(0.125, abs=1e-15)
    assert transformed[1, 0] == pytest.approx(
        math.cos(math.pi / 16.0) / (4.0 * math.sqrt(2.0)), abs=1e-15
    )
    assert transformed[0, 1] == pytest.approx(
        math.cos(3.0 * math.pi / 16.0) / (4.0 * math.sqrt(2.0)), abs=1e-15
    )


@pytest.mark.parametrize(
    ("bit", "expected"),
    [
        (0, (8.0, 0.0)),
        (1, (10.0, -2.0)),
    ],
)
def test_qim_uses_ties_to_even_then_the_requested_parity_lattice(bit, expected):
    embedded = qim_embed_pair(7.0, 1.0, bit=bit, delta=4.0)

    assert embedded == expected
    assert qim_extract_pair(*embedded, delta=4.0).bit == bit


@pytest.mark.parametrize(
    ("a", "b", "delta", "expected_bit", "expected_lattice"),
    [
        (4.0, 0.0, 4.0, 1, 1),
        (8.0, 0.0, 4.0, 0, 2),
        (-4.0, 0.0, 4.0, 1, -1),
    ],
)
def test_qim_extraction_has_independent_even_odd_bin_goldens(
    a, b, delta, expected_bit, expected_lattice
):
    extracted = qim_extract_pair(a, b, delta)

    assert extracted.bit == expected_bit
    assert extracted.lattice_index == expected_lattice
    assert 0.0 <= extracted.confidence <= 1.0


@pytest.mark.parametrize(
    ("operation", "message"),
    [
        (lambda: haar_dwt2(np.zeros((2, 2), dtype=np.float32)), "float64"),
        (lambda: haar_dwt2(np.zeros((2, 2, 1), dtype=np.float64)), "two-dimensional"),
        (lambda: dct2(np.zeros((4, 4), dtype=np.float64)), "8x8"),
        (lambda: qim_embed_pair(0.0, 0.0, bit=2, delta=4.0), "bit"),
        (lambda: qim_extract_pair(0.0, 0.0, delta=0.0), "delta"),
    ],
)
def test_transform_and_qim_boundaries_reject_ambiguous_inputs(operation, message):
    with pytest.raises((TypeError, ValueError), match=message):
        operation()


def test_band_embedding_rejects_a_codeword_above_exact_block_pair_capacity():
    detail_band = np.zeros((8, 8), dtype=np.float64)
    coefficient_pairs = (((1, 2), (2, 1)), ((2, 3), (3, 2)))

    with pytest.raises(ValueError, match=r"capacity is 2 bits.*needs 3"):
        embed_bits_in_band(
            detail_band,
            np.array([0, 1, 0], dtype=np.uint8),
            coefficient_pairs,
            delta=6.0,
        )
