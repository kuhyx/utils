# Copyright (c) 2026 Krzysztof Rudnicki
import numpy as np
import pytest

from music_theory import analysis, synth


def test_dominant_frequency_of_a_sine() -> None:
    assert analysis.dominant_frequency(synth.oscillator(1000.0, 1.0)) == pytest.approx(
        1000.0, abs=1.0
    )


def test_dominant_frequency_of_silence_and_empty() -> None:
    assert analysis.dominant_frequency(np.zeros(100)) == 0.0
    assert analysis.dominant_frequency(np.zeros(0)) == 0.0


def test_spectral_centroid_orders_timbres() -> None:
    sine = analysis.spectral_centroid(synth.oscillator(220.0, 0.5, "sine"))
    saw = analysis.spectral_centroid(synth.oscillator(220.0, 0.5, "saw"))
    assert sine < saw


def test_spectral_centroid_of_silence_and_empty() -> None:
    assert analysis.spectral_centroid(np.zeros(100)) == 0.0
    assert analysis.spectral_centroid(np.zeros(0)) == 0.0


def test_peak() -> None:
    assert analysis.peak(np.array([0.1, -0.7, 0.3])) == pytest.approx(0.7)
    assert analysis.peak(np.zeros(0)) == 0.0


def test_band_energy_finds_a_sine_in_its_band() -> None:
    signal = synth.oscillator(440.0, 0.5)
    inside = analysis.band_energy(signal, 400.0, 500.0)
    assert inside == pytest.approx(analysis.band_energy(signal, 0.0, 11025.0))
    assert analysis.band_energy(signal, 1000.0, 2000.0) < inside * 1e-6
    assert analysis.band_energy(np.zeros(0), 0.0, 100.0) == 0.0


def test_spectral_slope_of_white_noise_is_flat() -> None:
    rng = np.random.default_rng(1)
    white = rng.uniform(-1.0, 1.0, 44100)
    assert analysis.spectral_slope(white, 44100) == pytest.approx(0.0, abs=0.15)


def test_spectral_slope_of_a_falling_spectrum_is_negative() -> None:
    rng = np.random.default_rng(1)
    dark = synth.lowpass(rng.uniform(-1.0, 1.0, 22050), 200.0)
    assert analysis.spectral_slope(dark) < -1.0


def test_spectral_slope_needs_two_bands() -> None:
    with pytest.raises(ValueError, match="octave"):
        analysis.spectral_slope(np.ones(100), 22050, 1000.0, 1500.0)
