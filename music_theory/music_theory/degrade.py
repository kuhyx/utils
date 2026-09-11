# Copyright (c) 2026 Krzysztof Rudnicki
"""Degrade: the same piece, ruined by a controllable amount.

Not in the article, but built from its parts. If a composition is data,
"the ending is the opening, destroyed" is a transform on that data: the
mode darkens, the tempo drags, the melody thins out and drifts off pitch,
and the signal itself loses its top end and its resolution. Amount 0 is
the original, byte for byte; amount 1 is as far as this goes.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import numpy as np

from music_theory import synth

if TYPE_CHECKING:
    from music_theory.compose import Recipe

## Above this much degradation the mode flips to its darker relative.
MODE_THRESHOLD = 0.5

## Full degradation slows the tempo by this fraction.
TEMPO_DROP = 0.35

## Full degradation drops this fraction of melody notes.
MAX_REST_PROBABILITY = 0.5

## Full degradation lets each melody note drift up to this many cents.
MAX_DETUNE_CENTS = 30.0

## Low-pass cutoff sweeps from bright to muffled.
BRIGHT_CUTOFF_HZ = 9000.0
DARK_CUTOFF_HZ = 700.0

## Bit depth sweeps from clean 16-bit to a crunchy 8-bit.
CLEAN_BITS = 16.0
CRUSHED_BITS = 8.0

## Noise floor at full degradation, relative to full scale.
MAX_NOISE = 0.02

## Every bright mode's darker relative.
DARKER_MODE: dict[str, str] = {
    "major": "minor",
    "ionian": "aeolian",
    "lydian": "dorian",
    "mixolydian": "aeolian",
    "dorian": "phrygian",
    "major pentatonic": "minor pentatonic",
    "minor": "harmonic minor",
    "aeolian": "harmonic minor",
}


def clamp(amount: float) -> float:
    """Degrade amounts live in 0..1."""
    return min(max(amount, 0.0), 1.0)


def darker_mode(mode: str) -> str:
    """The mode one shade darker, or the same mode if there is none."""
    return DARKER_MODE.get(mode.lower(), mode)


def apply_to_recipe(recipe: Recipe) -> Recipe:
    """Darken the mode past the threshold and drag the tempo proportionally."""
    amount = clamp(recipe.degrade)
    mode = darker_mode(recipe.mode) if amount >= MODE_THRESHOLD else recipe.mode
    tempo = recipe.tempo_bpm * (1.0 - TEMPO_DROP * amount)
    return replace(recipe, mode=mode, tempo_bpm=tempo, degrade=amount)


def rest_probability(amount: float) -> float:
    """Chance a melody note is dropped."""
    return MAX_REST_PROBABILITY * clamp(amount)


def detune_cents(amount: float, rng: np.random.Generator) -> float:
    """A per-note pitch drift drawn from the seeded generator."""
    if amount <= 0.0:
        return 0.0
    return float(rng.uniform(-MAX_DETUNE_CENTS, MAX_DETUNE_CENTS) * clamp(amount))


def bitcrush(signal: synth.Signal, bits: float) -> synth.Signal:
    """Quantise to 2**bits levels."""
    levels = 2.0**bits
    return np.asarray(np.round(signal * levels) / levels, dtype=np.float64)


def process(
    signal: synth.Signal, amount: float, sample_rate: int, seed: int
) -> synth.Signal:
    """Low-pass, bit-crush and add noise in proportion to ``amount``."""
    amount = clamp(amount)
    if not amount:
        return signal.copy()
    cutoff = BRIGHT_CUTOFF_HZ + (DARK_CUTOFF_HZ - BRIGHT_CUTOFF_HZ) * amount
    bits = CLEAN_BITS + (CRUSHED_BITS - CLEAN_BITS) * amount
    rng = np.random.default_rng(seed)
    out = bitcrush(signal, bits)
    out = out + rng.standard_normal(len(out)) * MAX_NOISE * amount
    # FILTER LAST, TWICE. Crushing and noise both add broadband hiss; if the
    # low-pass ran first the result measured BRIGHTER than the original
    # (spectral centroid 2624 Hz against 2207 Hz on the first render). Two
    # one-pole passes give a real 12 dB/octave muffle.
    out = synth.lowpass(out, cutoff, sample_rate)
    return synth.lowpass(out, cutoff, sample_rate)
