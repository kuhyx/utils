# Copyright (c) 2026 Krzysztof Rudnicki
"""Score tokens: the words of a score line -- notes, drum steps, numbers.

Split from ``score`` so the line parser stays readable: each function here
reads one token and raises ``ValueError`` with what was wrong; ``score``
adds the line number.
"""

from __future__ import annotations

import math

from music_theory import pitch, sequencer, synth

REST = "-"
DRUM_STEP_BEATS = 0.5
_DRUM_STEPS: dict[str, sequencer.DrumKind | None] = {
    "k": "kick",
    "s": "snare",
    "h": "hat",
    ".": None,
}

## One step of a part: a MIDI note, a drum kind or a rest, and its length.
type Step = tuple[int | sequencer.DrumKind | None, float]
type Bar = tuple[Step, ...]


def positive(text: str, what: str) -> float:
    """``text`` as a finite number above zero."""
    try:
        value = float(text)
    except ValueError:
        value = 0.0
    if not value > 0.0 or not math.isfinite(value):
        msg = f"{what} must be a positive number, got {text!r}"
        raise ValueError(msg)
    return value


def count(text: str, what: str, minimum: int) -> int:
    """``text`` as a whole number of at least ``minimum``."""
    if not text.isdigit() or int(text) < minimum:
        msg = f"{what} must be an integer >= {minimum}, got {text!r}"
        raise ValueError(msg)
    return int(text)


def waveform(name: str) -> synth.Waveform:
    """The oscillator shape called ``name``."""
    for shape in synth.WAVEFORMS:
        if shape == name:
            return shape
    msg = f"unknown waveform {name!r}; choose one of {synth.WAVEFORMS}"
    raise ValueError(msg)


def note(token: str) -> Step:
    """``C5/2`` or ``-/1``: a MIDI note or rest, and its length in beats."""
    name, _, length = token.partition("/")
    beats = positive(length or "1", "note length")
    return (None if name == REST else pitch.parse_note(name), beats)


def drum_step(token: str) -> Step:
    """``k``, ``s``, ``h`` or ``.``: one eighth of kick, snare, hat or rest."""
    if token not in _DRUM_STEPS:
        msg = f"unknown drum step {token!r}; use k, s, h or ."
        raise ValueError(msg)
    return (_DRUM_STEPS[token], DRUM_STEP_BEATS)
