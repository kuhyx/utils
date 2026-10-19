# Copyright (c) 2026 Krzysztof Rudnicki
"""Noise: the sound of mass -- explosions, splashes, wind, gravel.

Not in the article, which is about pitched notes. A sound effect is mostly
unpitched, and noise is its raw material: white is every frequency at
once, pink tilts that by 3 dB per octave so it sounds even rather than
hissy, and grains chop either into sparse clicks (crackle, rattle).

Every source takes a ``numpy.random.Generator`` so a preset rendered with
the same seed is the same bytes, every time.
"""

from __future__ import annotations

import numpy as np

from music_theory.synth import SAMPLE_RATE, Signal


def white(frames: int, rng: np.random.Generator) -> Signal:
    """Uniform noise in [-1, 1): equal power at every frequency."""
    return rng.uniform(-1.0, 1.0, max(frames, 0))


def pink(frames: int, rng: np.random.Generator) -> Signal:
    """1/f noise, peak 1: white noise with each bin scaled by 1/sqrt(f).

    Power falls as 1/f, i.e. 3 dB per octave, so every octave holds the
    same energy -- the reason it sounds like rain or surf rather than hiss.
    Shaping in the frequency domain gives the exact slope at any length,
    where a running filter only approximates it.
    """
    source = white(frames, rng)
    if frames <= 1:
        return source
    spectrum = np.fft.rfft(source)
    scale = np.zeros(len(spectrum))
    scale[1:] = 1.0 / np.sqrt(np.arange(1, len(spectrum)))
    shaped = np.fft.irfft(spectrum * scale, n=frames)
    return np.asarray(shaped / np.max(np.abs(shaped)), dtype=np.float64)


def grains(
    frames: int,
    rate_hz: float,
    grain_seconds: float,
    rng: np.random.Generator,
    sample_rate: int = SAMPLE_RATE,
) -> Signal:
    """A 0..1 gate of short Hann bumps at Poisson-random times.

    Multiply a noise layer by it and it becomes crackle (fire, ~20/s) or a
    gravel rattle (earth, ~100/s): a few-millisecond grain is heard as a
    click, and the random spacing is what keeps it from sounding like a
    buzz at the grain rate.
    """
    gate = np.zeros(max(frames, 0), dtype=np.float64)
    if not gate.size or rate_hz <= 0.0:
        return gate
    count = int(rng.poisson(rate_hz * frames / sample_rate))
    width = max(int(grain_seconds * sample_rate), 1)
    bump = np.hanning(width + 2)[1:-1]
    for start in np.sort(rng.integers(0, frames, count)):
        end = min(int(start) + width, frames)
        gate[start:end] = np.maximum(gate[start:end], bump[: end - start])
    return gate
