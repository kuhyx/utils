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
