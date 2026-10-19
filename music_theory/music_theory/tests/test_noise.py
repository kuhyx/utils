# Copyright (c) 2026 Krzysztof Rudnicki
import numpy as np
import pytest

from music_theory import analysis, noise

RATE = 44100


def _rng(seed: int = 7) -> np.random.Generator:
    return np.random.default_rng(seed)


def test_white_is_flat_and_bounded() -> None:
    signal = noise.white(RATE, _rng())
    assert len(signal) == RATE
    assert float(np.max(np.abs(signal))) <= 1.0
    assert analysis.spectral_slope(signal, RATE) == pytest.approx(0.0, abs=0.3)


def test_pink_falls_three_db_per_octave() -> None:
    signal = noise.pink(RATE, _rng())
    assert len(signal) == RATE
    assert float(np.max(np.abs(signal))) == pytest.approx(1.0)
    assert analysis.spectral_slope(signal, RATE) == pytest.approx(-1.0, abs=0.3)


def test_pink_is_darker_than_white() -> None:
    white = analysis.spectral_centroid(noise.white(RATE, _rng()), RATE)
    pink = analysis.spectral_centroid(noise.pink(RATE, _rng()), RATE)
    # Amplitude ~ f^-1/2 puts the centroid at a third of Nyquist, white at half.
    assert pink < white * 0.75


def test_noise_is_seeded() -> None:
    assert np.array_equal(noise.white(500, _rng(3)), noise.white(500, _rng(3)))
    assert np.array_equal(noise.pink(500, _rng(3)), noise.pink(500, _rng(3)))
    assert not np.array_equal(noise.white(500, _rng(3)), noise.white(500, _rng(4)))


def test_empty_noise() -> None:
    assert noise.white(0, _rng()).size == 0
    assert noise.pink(0, _rng()).size == 0
    assert noise.pink(1, _rng()).size == 1


def test_grains_are_sparse_bumps_in_unit_range() -> None:
    gate = noise.grains(RATE, 20.0, 0.002, _rng(), RATE)
    assert len(gate) == RATE
    assert float(np.min(gate)) == 0.0
    assert float(np.max(gate)) <= 1.0
    onsets = int(np.sum((gate[1:] > 0.0) & (gate[:-1] == 0.0)))
    assert 8 <= onsets <= 32
    assert float(np.mean(gate > 0.0)) < 0.1


def test_grains_density_follows_the_rate() -> None:
    sparse = noise.grains(RATE, 10.0, 0.002, _rng(), RATE)
    dense = noise.grains(RATE, 200.0, 0.002, _rng(), RATE)
    assert float(np.mean(dense > 0.0)) > 5 * float(np.mean(sparse > 0.0))


def test_grains_without_rate_or_frames_are_silent() -> None:
    assert not np.any(noise.grains(100, 0.0, 0.002, _rng(), RATE))
    assert noise.grains(0, 20.0, 0.002, _rng(), RATE).size == 0
