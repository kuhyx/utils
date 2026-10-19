# Copyright (c) 2026 Krzysztof Rudnicki
from typing import cast

import numpy as np
import pytest

from music_theory import analysis, biquad

RATE = 44100
CUTOFF = 2000.0


@pytest.fixture(scope="module")
def white() -> np.ndarray:
    return np.random.default_rng(11).uniform(-1.0, 1.0, RATE // 2)


def _db(filtered: float, original: float) -> float:
    return float(10.0 * np.log10(filtered / original))


def test_highpass_removes_energy_below_the_cutoff(white: np.ndarray) -> None:
    out = biquad.biquad(white, "highpass", CUTOFF, sample_rate=RATE)
    # 12 dB/octave: two octaves below the cutoff is at least 20 dB down.
    below = (0.0, CUTOFF / 4)
    drop = _db(
        analysis.band_energy(out, *below, RATE),
        analysis.band_energy(white, *below, RATE),
    )
    assert drop < -20.0
    above = (4 * CUTOFF, 8 * CUTOFF)
    kept = _db(
        analysis.band_energy(out, *above, RATE),
        analysis.band_energy(white, *above, RATE),
    )
    assert kept > -1.0


def test_lowpass_removes_energy_above_the_cutoff(white: np.ndarray) -> None:
    out = biquad.biquad(white, "lowpass", CUTOFF, sample_rate=RATE)
    above = (2 * CUTOFF, 4 * CUTOFF)
    drop = _db(
        analysis.band_energy(out, *above, RATE),
        analysis.band_energy(white, *above, RATE),
    )
    assert drop < -10.0
    below = (0.0, CUTOFF / 4)
    kept = _db(
        analysis.band_energy(out, *below, RATE),
        analysis.band_energy(white, *below, RATE),
    )
    assert kept > -1.0


def test_bandpass_keeps_the_centre_and_cuts_both_sides(white: np.ndarray) -> None:
    out = biquad.biquad(white, "bandpass", 1000.0, q=8.0, sample_rate=RATE)

    def change(low: float, high: float) -> float:
        return _db(
            analysis.band_energy(out, low, high, RATE),
            analysis.band_energy(white, low, high, RATE),
        )

    assert change(950.0, 1050.0) > -3.0
    assert change(125.0, 250.0) < -15.0
    assert change(4000.0, 8000.0) < -15.0


def test_resonance_peaks_at_the_cutoff(white: np.ndarray) -> None:
    flat = biquad.biquad(white, "lowpass", CUTOFF, q=0.707, sample_rate=RATE)
    sharp = biquad.biquad(white, "lowpass", CUTOFF, q=8.0, sample_rate=RATE)
    band = (CUTOFF * 0.9, CUTOFF * 1.1)
    gain = _db(
        analysis.band_energy(sharp, *band, RATE),
        analysis.band_energy(flat, *band, RATE),
    )
    assert gain > 10.0


def test_a_swept_cutoff_brightens_over_time(white: np.ndarray) -> None:
    cutoff = np.geomspace(200.0, 10000.0, len(white))
    out = biquad.biquad(white, "lowpass", cutoff, sample_rate=RATE)
    half = len(out) // 2
    early = analysis.spectral_centroid(out[:half], RATE)
    late = analysis.spectral_centroid(out[half:], RATE)
    assert late > 3 * early


def test_cutoffs_beyond_nyquist_are_clamped_and_stay_finite(white: np.ndarray) -> None:
    out = biquad.biquad(white, "lowpass", 1e6, sample_rate=RATE)
    assert np.all(np.isfinite(out))
    assert float(np.max(np.abs(out))) < 4.0
    low = biquad.biquad(white, "highpass", 0.0, sample_rate=RATE)
    assert np.all(np.isfinite(low))


def test_empty_signal_passes_through() -> None:
    assert biquad.biquad(np.zeros(0), "bandpass", 500.0).size == 0


def test_rejects_bad_kind_q_and_cutoff_length() -> None:
    signal = np.zeros(10)
    with pytest.raises(ValueError, match="unknown filter"):
        biquad.biquad(signal, cast("biquad.FilterKind", "notch"), 500.0)
    with pytest.raises(ValueError, match="q must be positive"):
        biquad.biquad(signal, "lowpass", 500.0, q=0.0)
    with pytest.raises(ValueError, match="one cutoff per sample"):
        biquad.biquad(signal, "lowpass", np.full(3, 500.0))
