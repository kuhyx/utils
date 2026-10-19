# Copyright (c) 2026 Krzysztof Rudnicki
"""Biquad: low-, high- and band-pass filters with resonance, cutoff may move.

``synth.lowpass`` is one pole: a gentle 6 dB/octave darkening with no
resonance and no other shapes. Sound effects need more -- a high-pass to
thin a crack, a resonant band-pass whose centre sweeps to make a whoosh.
These are the two-pole filters from Robert Bristow-Johnson's "Audio EQ
Cookbook", 12 dB/octave, with ``q`` as the resonance (0.707 = no peak).

The cutoff can be a per-sample curve. Coefficients are recomputed once per
``BLOCK`` samples, not per sample: a sweep is far slower than 1.5 ms, and
the per-sample loop is the part that costs.
"""

from __future__ import annotations

import math
from typing import Literal

import numpy as np

from music_theory.synth import SAMPLE_RATE, Signal

type FilterKind = Literal["lowpass", "highpass", "bandpass"]

FILTER_KINDS: tuple[FilterKind, ...] = ("lowpass", "highpass", "bandpass")

## Butterworth: the steepest response with no resonant bump.
FLAT_Q = 1.0 / math.sqrt(2.0)

## Samples per coefficient update (~1.5 ms at 44.1 kHz).
BLOCK = 64

## Cutoffs are kept inside this audible, numerically safe range.
_MIN_HZ = 10.0
_MAX_FRACTION_OF_RATE = 0.49

type Coefficients = tuple[Signal, Signal, Signal, Signal, Signal]


def coefficients(
    kind: FilterKind, cutoff: Signal, q: float, sample_rate: int = SAMPLE_RATE
) -> Coefficients:
    """Normalised (b0, b1, b2, a1, a2) for every cutoff, vectorised."""
    hz = np.clip(cutoff, _MIN_HZ, _MAX_FRACTION_OF_RATE * sample_rate)
    w0 = 2.0 * math.pi * hz / sample_rate
    cos_w0 = np.cos(w0)
    alpha = np.sin(w0) / (2.0 * q)
    a0 = 1.0 + alpha
    if kind == "lowpass":
        b0 = (1.0 - cos_w0) / 2.0
        b1 = 1.0 - cos_w0
        b2 = b0
    elif kind == "highpass":
        b0 = (1.0 + cos_w0) / 2.0
        b1 = -(1.0 + cos_w0)
        b2 = b0
    else:
        b0 = alpha
        b1 = np.zeros_like(alpha)
        b2 = -alpha
    return (b0 / a0, b1 / a0, b2 / a0, -2.0 * cos_w0 / a0, (1.0 - alpha) / a0)


def _cutoff_curve(cutoff: float | Signal, frames: int) -> Signal:
    curve = np.broadcast_to(np.asarray(cutoff, dtype=np.float64), (frames,))
    return np.asarray(curve, dtype=np.float64)


def _validate(kind: FilterKind, q: float, cutoff: float | Signal, frames: int) -> None:
    if kind not in FILTER_KINDS:
        msg = f"unknown filter {kind!r}; choose one of {FILTER_KINDS}"
        raise ValueError(msg)
    if q <= 0.0:
        msg = f"q must be positive, got {q}"
        raise ValueError(msg)
    if np.ndim(cutoff) and np.size(cutoff) != frames:
        msg = f"need one cutoff per sample: {np.size(cutoff)} for {frames}"
        raise ValueError(msg)


def _run(samples: list[float], blocks: list[tuple[float, ...]]) -> list[float]:
    """The per-sample loop, in plain floats (numpy scalars are ~10x slower).

    Transposed direct form II: two state values, and it tolerates the
    coefficients changing between blocks without blowing up.
    """
    out = [0.0] * len(samples)
    z1 = z2 = 0.0
    for start, (c0, c1, c2, d1, d2) in zip(
        range(0, len(samples), BLOCK), blocks, strict=True
    ):
        for index in range(start, min(start + BLOCK, len(samples))):
            x = samples[index]
            y = c0 * x + z1
            z1 = c1 * x - d1 * y + z2
            z2 = c2 * x - d2 * y
            out[index] = y
    return out


def biquad(
    signal: Signal,
    kind: FilterKind,
    cutoff: float | Signal,
    q: float = FLAT_Q,
    sample_rate: int = SAMPLE_RATE,
) -> Signal:
    """Filter ``signal``; ``cutoff`` is Hz, constant or one value per sample."""
    _validate(kind, q, cutoff, len(signal))
    curve = _cutoff_curve(cutoff, len(signal))[::BLOCK]
    columns = (c.tolist() for c in coefficients(kind, curve, q, sample_rate))
    blocks = list(zip(*columns, strict=True))
    return np.asarray(_run(signal.tolist(), blocks), dtype=np.float64)
