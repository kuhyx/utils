# Copyright (c) 2026 Krzysztof Rudnicki
"""Analysis: measure a rendered signal so a claim about it can be checked.

Not in the article, but every demo here makes a claim ("this is 440 Hz",
"this is darker") and a claim about audio that only a listener can verify
is one the test suite cannot hold. These measurements let it: the peak and
centroid for pitch and brightness, band energy for "the filter removed
that", and the octave-band slope for "this noise is white / pink".
"""

from __future__ import annotations

from itertools import pairwise

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


## An octave-band slope needs at least this many bands to fit a line.
_MIN_BANDS = 2


def _power(signal: Signal, sample_rate: int) -> tuple[Signal, Signal]:
    """Frequency bins and the power in each."""
    power = np.abs(np.fft.rfft(signal)) ** 2
    return np.fft.rfftfreq(len(signal), d=1.0 / sample_rate), power


def band_energy(
    signal: Signal, low_hz: float, high_hz: float, sample_rate: int = SAMPLE_RATE
) -> float:
    """Spectral power in ``[low_hz, high_hz)``: "is there energy below the cutoff"."""
    if not signal.size:
        return 0.0
    bins, power = _power(signal, sample_rate)
    return float(np.sum(power[(bins >= low_hz) & (bins < high_hz)]))


def spectral_slope(
    signal: Signal,
    sample_rate: int = SAMPLE_RATE,
    low_hz: float = 100.0,
    high_hz: float = 8000.0,
) -> float:
    """Slope of log power density against log frequency, over octave bands.

    White noise is flat (0), pink falls 3 dB per octave (-1), brown -2.
    Octave bands, not raw bins: a single bin of noise is itself noise, but
    the mean over an octave is steady enough to fit a line through.
    """
    edges = low_hz * 2.0 ** np.arange(int(np.log2(high_hz / low_hz)) + 1)
    if len(edges) <= _MIN_BANDS:
        msg = f"{low_hz}..{high_hz} Hz spans fewer than {_MIN_BANDS} octave bands"
        raise ValueError(msg)
    bins, power = _power(signal, sample_rate)
    centres = np.sqrt(edges[:-1] * edges[1:])
    density = np.array(
        [np.mean(power[(bins >= lo) & (bins < hi)]) for lo, hi in pairwise(edges)]
    )
    slope = np.polyfit(np.log2(centres), np.log2(density), 1)[0]
    return float(slope)
