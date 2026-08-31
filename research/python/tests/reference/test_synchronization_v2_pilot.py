from __future__ import annotations

import hashlib

import numpy as np
import pytest

import splitbind_ref.synchronization_v2 as synchronization_v2
from splitbind_ref.fingerprint_v2_profile import load_v2_profiles
from splitbind_ref.synchronization_v2 import (
    PilotTemplateV2,
    embed_pilot_v2,
    score_pilot_v2,
    synthesize_pilot_v2,
)


KEY = bytes(range(32))


@pytest.fixture
def profile():
    return load_v2_profiles()[0]


@pytest.fixture
def gradient():
    y, x = np.indices((384, 512), dtype=np.float64)
    return 32.0 + 170.0 * x / 511.0 + 45.0 * y / 383.0


def test_pilot_is_deterministic_zero_mean_unit_rms(profile):
    template = synthesize_pilot_v2((384, 512), KEY, 0, profile)
    repeated = synthesize_pilot_v2((384, 512), KEY, 0, profile)

    assert template.page_shape == (384, 512)
    assert template.spatial.shape == (384, 512)
    assert template.spatial.dtype == np.float64
    assert template.frequency_pairs.dtype == np.float64
    assert np.array_equal(template.frequency_pairs, repeated.frequency_pairs)
    assert np.array_equal(template.spatial, repeated.spatial)
    assert float(template.spatial.mean()) == pytest.approx(0.0, abs=1e-12)
    assert float(np.sqrt(np.mean(template.spatial**2))) == pytest.approx(
        1.0, abs=1e-12
    )
    assert len(template.frequency_pairs) == 12
    assert np.isfinite(template.frequency_pairs).all()
    assert np.isfinite(template.spatial).all()


def test_frequency_constellation_obeys_radius_axis_and_pair_clearances(profile):
    frequencies = synthesize_pilot_v2((96, 128), KEY, 0, profile).frequency_pairs
    radii = np.linalg.norm(frequencies, axis=1)

    assert np.all(radii >= 0.08)
    assert np.all(radii <= 0.18)
    assert np.all(np.abs(frequencies) >= 0.02)
    for index, frequency in enumerate(frequencies):
        others = frequencies[index + 1 :]
        if len(others):
            assert np.all(np.linalg.norm(others - frequency, axis=1) >= 0.015)
            assert np.all(np.linalg.norm(others + frequency, axis=1) >= 0.015)


def test_frequency_constellation_retains_deterministic_asymmetry(profile):
    frequencies = synthesize_pilot_v2((96, 128), KEY, 0, profile).frequency_pairs
    reflected = frequencies * np.array([1.0, -1.0])
    reflection_distances = np.linalg.norm(
        frequencies[:, None, :] - reflected[None, :, :], axis=2
    )

    assert not np.allclose(np.sort(frequencies[:, 0]), np.sort(frequencies[:, 1]))
    assert np.all(reflection_distances >= 0.015)


def test_pilot_template_makes_exact_defensive_contiguous_read_only_copies():
    frequencies = np.arange(48, dtype=np.float64).reshape(24, 2)[::2]
    spatial = np.arange(48, dtype=np.float64).reshape(6, 8)[:, ::-1]
    expected_frequencies = frequencies.copy()
    expected_spatial = spatial.copy()

    template = PilotTemplateV2((6, 8), frequencies, spatial)
    frequencies[:] = -1.0
    spatial[:] = -1.0

    assert np.array_equal(template.frequency_pairs, expected_frequencies)
    assert np.array_equal(template.spatial, expected_spatial)
    assert template.frequency_pairs.flags.c_contiguous
    assert template.spatial.flags.c_contiguous
    assert not template.frequency_pairs.flags.writeable
    assert not template.spatial.flags.writeable


def test_gradient_needs_no_natural_features_for_pilot(profile, gradient):
    template = synthesize_pilot_v2(gradient.shape, KEY, 0, profile)
    embedded = embed_pilot_v2(gradient, template, profile.pilot_strength_rms)

    assert score_pilot_v2(embedded, template) >= profile.pilot_score_min


def test_wrong_key_page_and_profile_remain_below_pilot_threshold(profile, gradient):
    template = synthesize_pilot_v2(gradient.shape, KEY, 0, profile)
    embedded = embed_pilot_v2(gradient, template, profile.pilot_strength_rms)
    wrong_templates = (
        synthesize_pilot_v2(gradient.shape, b"w" * 32, 0, profile),
        synthesize_pilot_v2(gradient.shape, KEY, 1, profile),
        synthesize_pilot_v2(gradient.shape, KEY, 0, load_v2_profiles()[4]),
    )

    assert all(
        score_pilot_v2(embedded, wrong_template) < profile.pilot_score_min
        for wrong_template in wrong_templates
    )


def test_first_128_wrong_pages_remain_below_pilot_threshold(profile, gradient):
    template = synthesize_pilot_v2(gradient.shape, KEY, 0, profile)
    embedded = embed_pilot_v2(gradient, template, profile.pilot_strength_rms)
    wrong_page_scores = {
        page_index: score_pilot_v2(
            embedded,
            synthesize_pilot_v2(gradient.shape, KEY, page_index, profile),
        )
        for page_index in range(1, 129)
    }
    worst_page, worst_score = max(
        wrong_page_scores.items(), key=lambda item: item[1]
    )

    assert worst_score < profile.pilot_score_min, (worst_page, worst_score)


def test_embedding_is_additive_float64_finite_and_does_not_mutate_input(profile):
    luminance = np.arange(96 * 128, dtype=np.uint8).reshape(96, 128)
    original = luminance.copy()
    template = synthesize_pilot_v2(luminance.shape, KEY, 0, profile)

    embedded = embed_pilot_v2(luminance, template, 200.0)

    assert embedded.dtype == np.float64
    assert embedded.flags.c_contiguous
    assert np.isfinite(embedded).all()
    assert np.array_equal(luminance, original)
    assert np.array_equal(
        embedded, luminance.astype(np.float64) + 200.0 * template.spatial
    )
    assert float(embedded.min()) < 0.0
    assert float(embedded.max()) > 255.0


def test_scoring_returns_finite_bounded_values_and_zero_for_zero_energy(profile):
    template = synthesize_pilot_v2((96, 128), KEY, 0, profile)

    assert score_pilot_v2(np.zeros((96, 128)), template) == 0.0
    assert score_pilot_v2(np.full((96, 128), 127.0), template) == 0.0
    for luminance in (template.spatial, -template.spatial):
        score = score_pilot_v2(luminance, template)
        assert np.isfinite(score)
        assert -1.0 <= score <= 1.0


def test_scoring_downsamples_both_fft_inputs_to_a_2048_pixel_long_edge(
    profile, monkeypatch
):
    shape = (1025, 2049)
    template = synthesize_pilot_v2(shape, KEY, 0, profile)
    luminance = embed_pilot_v2(np.zeros(shape), template, 2.0)
    observed_shapes = []
    real_rfft2 = np.fft.rfft2

    def recording_rfft2(array, *args, **kwargs):
        observed_shapes.append(array.shape)
        return real_rfft2(array, *args, **kwargs)

    monkeypatch.setattr(synchronization_v2.np.fft, "rfft2", recording_rfft2)

    score_pilot_v2(luminance, template)

    assert len(observed_shapes) == 2
    assert observed_shapes[0] == observed_shapes[1]
    assert max(observed_shapes[0]) == 2048


@pytest.mark.parametrize(
    "operation",
    [
        lambda profile, oversized: synthesize_pilot_v2(
            (40_000_001, 1), KEY, 0, profile
        ),
        lambda profile, oversized: embed_pilot_v2(
            oversized,
            PilotTemplateV2(
                (1, 1),
                np.zeros((12, 2), dtype=np.float64),
                np.zeros((1, 1), dtype=np.float64),
            ),
            1.0,
        ),
        lambda profile, oversized: score_pilot_v2(
            oversized,
            PilotTemplateV2(
                (1, 1),
                np.zeros((12, 2), dtype=np.float64),
                np.zeros((1, 1), dtype=np.float64),
            ),
        ),
    ],
    ids=["synthesis", "embedding", "scoring"],
)
def test_operations_reject_over_40_megapixels_before_expensive_allocation(
    profile, operation
):
    oversized = np.broadcast_to(np.zeros((1, 1), dtype=np.float64), (40_000_001, 1))

    with pytest.raises(ValueError, match="40-megapixel"):
        operation(profile, oversized)


@pytest.mark.parametrize(
    ("call", "error", "message"),
    [
        (lambda profile: synthesize_pilot_v2((0, 64), KEY, 0, profile), ValueError, "positive"),
        (lambda profile: synthesize_pilot_v2((64, 64), b"", 0, profile), ValueError, "key"),
        (lambda profile: synthesize_pilot_v2((64, 64), KEY, -1, profile), ValueError, "page_index"),
        (lambda profile: embed_pilot_v2(np.zeros((64, 63)), synthesize_pilot_v2((64, 64), KEY, 0, profile), 1.0), ValueError, "shape"),
        (lambda profile: embed_pilot_v2(np.full((64, 64), np.nan), synthesize_pilot_v2((64, 64), KEY, 0, profile), 1.0), ValueError, "finite"),
        (lambda profile: embed_pilot_v2(np.zeros((64, 64), dtype=np.complex128), synthesize_pilot_v2((64, 64), KEY, 0, profile), 1.0), TypeError, "real numeric"),
        (lambda profile: embed_pilot_v2(np.zeros((64, 64)), synthesize_pilot_v2((64, 64), KEY, 0, profile), np.inf), ValueError, "strength"),
    ],
)
def test_pilot_api_rejects_invalid_inputs(profile, call, error, message):
    with pytest.raises(error, match=message):
        call(profile)


def test_pilot_golden_hashes_pin_frequency_and_spatial_determinism(profile):
    template = synthesize_pilot_v2((96, 128), KEY, 7, profile)

    assert hashlib.sha256(template.frequency_pairs.tobytes()).hexdigest() == (
        "0d7f93dce5e9c2f1d0aa57665f40bc83d14150ea7844bfae34c09a1f4977526c"
    )
    assert hashlib.sha256(template.spatial.tobytes()).hexdigest() == (
        "5620d4f91446446c6ab211a8205f4a841325615d1bfe0b22fa905d58c53eecd5"
    )
