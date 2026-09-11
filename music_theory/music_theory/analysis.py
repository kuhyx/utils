# Copyright (c) 2026 Krzysztof Rudnicki
"""Analysis: measure a rendered signal so a claim about it can be checked.

Not in the article, but every demo here makes a claim ("this is 440 Hz",
"this is darker") and a claim about audio that only a listener can verify
is one the test suite cannot hold. These two measurements let it.
"""

from __future__ import annotations

import numpy as np

from music_theory.synth import SAMPLE_RATE, Signal


def dominant_frequency(signal: Signal, sample_rate: int = SAMPLE_RATE) -> float:
    """Frequency of the strongest FFT bin, in Hz (0.0 for silence)."""
    if not signal.size:
        return 0.0
    spectrum = np.abs(np.fft.rfft(signal))
    if not np.any(spectrum > 0.0):
        return 0.0
    bins = np.fft.rfftfreq(len(signal), d=1.0 / sample_rate)
    return float(bins[int(np.argmax(spectrum))])


def spectral_centroid(signal: Signal, sample_rate: int = SAMPLE_RATE) -> float:
    """Amplitude-weighted mean frequency: lower means darker."""
    if not signal.size:
        return 0.0
    spectrum = np.abs(np.fft.rfft(signal))
    total = float(np.sum(spectrum))
    if not total:
        return 0.0
    bins = np.fft.rfftfreq(len(signal), d=1.0 / sample_rate)
    return float(np.sum(bins * spectrum) / total)


def peak(signal: Signal) -> float:
    """Loudest absolute sample value."""
    return float(np.max(np.abs(signal))) if len(signal) else 0.0
