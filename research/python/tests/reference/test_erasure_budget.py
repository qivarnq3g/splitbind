import numpy as np
import pytest

from splitbind_ref.ecc import (
    EccDecodeError,
    decode_ecc_with_erasures,
    encode_ecc,
    erasure_budget,
    erasure_ladder,
    rank_erasure_candidates,
)
from splitbind_ref.fingerprint_v2_codec import CodewordEvidence as CodewordEvidenceV2
from splitbind_ref.fingerprint_v3_dct import CodewordEvidence


PARITY_SYMBOLS = erasure_budget()
CODEWORD_BYTES = 39


def ladder_for(item):
    return erasure_ladder(item.erase_positions, item.erasure_ranking)


def evidence(erase_positions, ranking, codeword=bytes(CODEWORD_BYTES)):
    return CodewordEvidence(
        codeword=codeword,
        erase_positions=tuple(erase_positions),
        mean_confidence=0.5,
        bit_error_hint=None,
        erasure_ranking=tuple(ranking),
    )


def test_ranking_orders_the_least_reliable_byte_first():
    confidence = np.array([0.9, 0.1, 0.5, 0.3], dtype=np.float64)

    assert rank_erasure_candidates(confidence) == (1, 3, 2, 0)


def test_ranking_breaks_confidence_ties_by_position():
    confidence = np.array([0.4, 0.4, 0.4], dtype=np.float64)

    assert rank_erasure_candidates(confidence) == (0, 1, 2)


def test_ladder_offers_the_reported_erasures_first():
    ladder = list(ladder_for(evidence((3, 7), range(CODEWORD_BYTES))))

    assert ladder[0] == (3, 7)


def test_ladder_retreats_to_sets_the_parity_budget_can_absorb():
    over_budget = tuple(range(24))
    ladder = list(ladder_for(evidence(over_budget, range(CODEWORD_BYTES))))

    assert ladder[0] == over_budget
    assert all(len(attempt) <= PARITY_SYMBOLS for attempt in ladder[1:])
    assert ladder[-1] == ()


def test_ladder_never_repeats_an_attempt():
    ladder = list(ladder_for(evidence((), range(CODEWORD_BYTES))))

    assert len(ladder) == len(set(ladder))


def test_reed_solomon_refuses_more_erasures_than_it_has_parity_symbols():
    codeword = encode_ecc(bytes(range(CODEWORD_BYTES - PARITY_SYMBOLS)))

    decode_ecc_with_erasures(codeword, tuple(range(PARITY_SYMBOLS)))
    with pytest.raises(EccDecodeError):
        decode_ecc_with_erasures(codeword, tuple(range(PARITY_SYMBOLS + 1)))


def test_a_clean_codeword_survives_an_over_eager_erasure_claim():
    payload = bytes(range(CODEWORD_BYTES - PARITY_SYMBOLS))
    codeword = encode_ecc(payload)
    over_eager = evidence(tuple(range(24)), range(CODEWORD_BYTES), codeword)

    recovered = None
    for erasures in ladder_for(over_eager):
        try:
            recovered = decode_ecc_with_erasures(codeword, erasures)
        except (EccDecodeError, ValueError):
            continue
        break

    assert recovered == payload


def test_the_budget_matches_the_frozen_payload_contract():
    assert erasure_budget() == PARITY_SYMBOLS


def test_both_codec_generations_expose_a_reliability_ranking():
    confidence = np.linspace(0.1, 0.9, CODEWORD_BYTES)
    ranking = rank_erasure_candidates(confidence)

    v3 = CodewordEvidence(bytes(CODEWORD_BYTES), (), 0.5, None, ranking)
    v2 = CodewordEvidenceV2(bytes(CODEWORD_BYTES), (), 0.5, None, ranking)

    assert ladder_for(v3) == ladder_for(v2)
    assert all(len(attempt) <= PARITY_SYMBOLS for attempt in ladder_for(v2))
