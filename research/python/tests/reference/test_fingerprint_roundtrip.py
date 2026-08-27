import itertools
import math
from pathlib import Path
from uuid import UUID

import numpy as np
import pytest

import splitbind_ref.fingerprint as fingerprint_module
from splitbind_ref.contracts import fingerprint_candidates
from splitbind_ref.fingerprint import (
    DecodeVote,
    FingerprintContext,
    decode_fingerprint,
    embed_fingerprint,
    soft_vote,
)
from splitbind_ref.payload import encode_payload


ISSUANCE_ID = UUID("12345678-1234-5678-1234-567812345678")
OTHER_ISSUANCE_ID = UUID("87654321-4321-8765-4321-876543218765")
KEY = bytes.fromhex("00112233445566778899aabbccddeeff" * 2)
NONCE = bytes.fromhex("fedcba98765432100123456789abcdef")
PAGE_INDEX = 2
ROOT = Path(__file__).resolve().parents[4]


def _candidate_profiles():
    contract = fingerprint_candidates()
    keys = ("qim_delta", "tile_size_px", "tiles_per_page", "payload_repetitions")
    return [
        {
            "schema_version": contract["schema_version"],
            **dict(zip(keys, combination, strict=True)),
            "document_nonce": NONCE,
            "page_index": PAGE_INDEX,
        }
        for combination in itertools.product(*(contract["sweep"][key] for key in keys))
    ]


CANDIDATE_PROFILES = _candidate_profiles()


@pytest.fixture(scope="module")
def sample_page():
    height, width = 1536, 2304
    y, x = np.indices((height, width), dtype=np.int32)
    page = np.empty((height, width, 3), dtype=np.uint8)
    page[..., 0] = 48 + ((3 * x + y) % 144)
    page[..., 1] = 52 + ((x + 2 * y) % 136)
    page[..., 2] = 56 + ((2 * x + 3 * y) % 128)
    for offset in range(96, min(height, width), 192):
        page[offset : offset + 7, 40 : width - 40] = (215, 215, 215)
        page[40 : height - 40, offset : offset + 7] = (32, 32, 32)
    return page


@pytest.fixture
def embed_context():
    return FingerprintContext(
        issuance_id=ISSUANCE_ID,
        fingerprint_key=KEY,
        document_nonce=NONCE,
        page_index=PAGE_INDEX,
    )


@pytest.fixture
def candidate_profile():
    return {
        "schema_version": 1,
        "qim_delta": 12.0,
        "tile_size_px": 256,
        "tiles_per_page": 12,
        "payload_repetitions": 5,
        "document_nonce": NONCE,
        "page_index": PAGE_INDEX,
    }


@pytest.mark.parametrize(
    "profile",
    CANDIDATE_PROFILES,
    ids=lambda profile: (
        f"d{profile['qim_delta']}-t{profile['tile_size_px']}-"
        f"n{profile['tiles_per_page']}-r{profile['payload_repetitions']}"
    ),
)
def test_every_contracted_candidate_has_a_clean_measured_roundtrip(
    sample_page, embed_context, profile
):
    embedded = embed_fingerprint(sample_page, embed_context, profile)
    decoded = decode_fingerprint(embedded.image, KEY, (profile,))

    assert decoded.issuance_id == ISSUANCE_ID
    assert decoded.reason == "decoded"
    assert decoded.valid_votes == profile["payload_repetitions"]
    assert decoded.confidence >= 0.95
    error = embedded.image.astype(np.float64) - sample_page.astype(np.float64)
    mse = float(np.mean(error * error))
    measured_psnr = math.inf if mse == 0.0 else 10.0 * math.log10(255.0**2 / mse)
    assert measured_psnr == pytest.approx(embedded.psnr_db, abs=1e-12)
    assert measured_psnr >= 30.0  # provisional unit tolerance; A4/A5 own release evidence


def test_wrong_key_nonce_and_page_binding_never_attribute(
    sample_page, embed_context, candidate_profile
):
    embedded = embed_fingerprint(sample_page, embed_context, candidate_profile)

    wrong_key = decode_fingerprint(embedded.image, b"w" * 32, (candidate_profile,))
    wrong_nonce = decode_fingerprint(
        embedded.image,
        KEY,
        ({**candidate_profile, "document_nonce": bytes(16)},),
    )
    wrong_page = decode_fingerprint(
        embedded.image,
        KEY,
        ({**candidate_profile, "page_index": PAGE_INDEX + 1},),
    )

    assert wrong_key.issuance_id is None
    assert wrong_nonce.issuance_id is None
    assert wrong_page.issuance_id is None


def test_roundtrip_consumes_the_versioned_a1_clean_image_corpus(
    embed_context, candidate_profile
):
    import cv2

    corpus_page = cv2.imread(
        str(ROOT / "fixtures/corpus/generated/clean-mixed-contrast.png"),
        cv2.IMREAD_COLOR,
    )
    assert corpus_page is not None
    page = cv2.resize(corpus_page, (2304, 1536), interpolation=cv2.INTER_NEAREST)

    embedded = embed_fingerprint(page, embed_context, candidate_profile)
    decoded = decode_fingerprint(embedded.image, KEY, (candidate_profile,))

    assert decoded.issuance_id == ISSUANCE_ID
    assert decoded.reason == "decoded"


def test_versioned_a1_negative_corpus_never_attributes(candidate_profile):
    import cv2

    negative = cv2.imread(
        str(ROOT / "fixtures/corpus/generated/negative-external-00.png"),
        cv2.IMREAD_COLOR,
    )
    assert negative is not None
    page = cv2.resize(negative, (2304, 1536), interpolation=cv2.INTER_NEAREST)

    decoded = decode_fingerprint(page, KEY, (candidate_profile,))

    assert decoded.issuance_id is None
    assert decoded.reason in {"not_detected", "invalid_crc"}


def test_valid_ecc_with_a_corrupted_crc_never_attributes(
    sample_page, embed_context, candidate_profile, monkeypatch
):
    corrupted = bytearray(encode_payload(ISSUANCE_ID))
    corrupted[-1] ^= 0x01
    monkeypatch.setattr(
        fingerprint_module,
        "encode_payload",
        lambda issuance_id, version=1: bytes(corrupted),
    )

    embedded = embed_fingerprint(sample_page, embed_context, candidate_profile)
    decoded = decode_fingerprint(embedded.image, KEY, (candidate_profile,))

    assert decoded.issuance_id is None
    assert decoded.reason == "invalid_crc"


@pytest.mark.parametrize("attack", ["brightness", "seeded_noise"])
def test_deterministic_mild_attacks_have_measured_unit_roundtrips(
    sample_page, embed_context, candidate_profile, attack
):
    embedded = embed_fingerprint(sample_page, embed_context, candidate_profile)
    if attack == "brightness":
        attacked = np.clip(embedded.image.astype(np.int16) + 4, 0, 255).astype(np.uint8)
    else:
        rng = np.random.default_rng(20260827)
        noise = rng.normal(0.0, 0.25, size=embedded.image.shape)
        attacked = np.clip(
            np.floor(embedded.image.astype(np.float64) + noise + 0.5), 0, 255
        ).astype(np.uint8)

    decoded = decode_fingerprint(attacked, KEY, (candidate_profile,))

    assert decoded.issuance_id == ISSUANCE_ID
    assert decoded.reason == "decoded"
    assert decoded.valid_votes == 5


def test_decode_uses_orb_ransac_alignment_before_extracting_tiles(
    sample_page, embed_context, candidate_profile
):
    import cv2

    embedded = embed_fingerprint(sample_page, embed_context, candidate_profile)
    height, width = embedded.image.shape[:2]
    transform = cv2.getRotationMatrix2D(
        ((width - 1) / 2.0, (height - 1) / 2.0), 0.35, 1.0
    )
    transform[:, 2] += np.array([3.0, -2.0])
    attacked = cv2.warpAffine(
        embedded.image,
        transform,
        (width, height),
        # A3 verifies the alignment/extraction path with one deterministic
        # resampling policy.  The A4 attack matrix owns bilinear/screenshot rates.
        flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_REFLECT_101,
    )

    decoded = decode_fingerprint(
        attacked,
        KEY,
        ({**candidate_profile, "sync_template": embedded.sync_template},),
    )

    assert decoded.issuance_id == ISSUANCE_ID
    assert decoded.reason == "decoded"


def test_embedding_preserves_chroma_away_from_clipping(
    sample_page, embed_context, candidate_profile
):
    embedded = embed_fingerprint(sample_page, embed_context, candidate_profile)
    interior = np.all((sample_page > 8) & (sample_page < 247), axis=2)
    original_chroma = sample_page.astype(np.int16)[..., :2] - sample_page.astype(
        np.int16
    )[..., 1:]
    embedded_chroma = embedded.image.astype(np.int16)[..., :2] - embedded.image.astype(
        np.int16
    )[..., 1:]

    assert np.max(np.abs(embedded_chroma[interior] - original_chroma[interior])) <= 1


def test_embedding_clips_to_and_preserves_a_uint16_page_bit_depth(
    sample_page, embed_context, candidate_profile
):
    page_uint16 = sample_page.astype(np.uint16) * np.uint16(257)

    embedded = embed_fingerprint(page_uint16, embed_context, candidate_profile)
    decoded = decode_fingerprint(embedded.image, KEY, (candidate_profile,))

    assert embedded.image.dtype == np.uint16
    assert int(embedded.image.min()) >= 0
    assert int(embedded.image.max()) <= np.iinfo(np.uint16).max
    assert decoded.issuance_id == ISSUANCE_ID


def test_soft_vote_requires_weighted_consensus_and_ignores_invalid_votes():
    votes = (
        DecodeVote(ISSUANCE_ID, 0.9, 0.01, "decoded"),
        DecodeVote(ISSUANCE_ID, 0.7, 0.03, "decoded"),
        DecodeVote(OTHER_ISSUANCE_ID, 0.8, 0.02, "decoded"),
        DecodeVote(None, 1.0, None, "invalid_crc"),
    )

    decoded = soft_vote(votes, threshold=0.65)
    partial = soft_vote(votes, threshold=0.80)

    assert decoded.issuance_id == ISSUANCE_ID
    assert decoded.reason == "decoded"
    assert decoded.valid_votes == 2
    assert decoded.confidence == pytest.approx(2.0 / 3.0)
    assert partial.issuance_id is None
    assert partial.reason == "partial"


@pytest.mark.parametrize(
    ("page", "profile_update", "message"),
    [
        (np.zeros((512, 512), dtype=np.uint8), {}, "BGR"),
        (np.zeros((512, 512, 3), dtype=np.float32), {}, "unsigned"),
        (np.zeros((255, 1024, 3), dtype=np.uint8), {}, "page"),
        (None, {"qim_delta": 7.0}, "qim_delta"),
        (None, {"payload_repetitions": 13}, "repetitions"),
    ],
)
def test_embedding_rejects_shape_type_capacity_and_uncontracted_profile_values(
    sample_page, embed_context, candidate_profile, page, profile_update, message
):
    actual_page = sample_page if page is None else page
    with pytest.raises((TypeError, ValueError), match=message):
        embed_fingerprint(
            actual_page,
            embed_context,
            {**candidate_profile, **profile_update},
        )
