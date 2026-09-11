# Copyright (c) 2026 Krzysztof Rudnicki
"""Pitch: the arithmetic between a MIDI number, a note name and a frequency.

Article section 1 and 5. Pitch perception is MULTIPLICATIVE -- going up one
semitone always multiplies the frequency by the same factor, never adds the
same number of hertz -- so every conversion here is an exponent, and the
MIDI number is simply that exponent counted in twelfths from A4 = 440 Hz.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

## The reference every other pitch is derived from.
A4_HZ = 440.0
A4_MIDI = 69

## Twelve equal steps per octave (why twelve: see ``tuning.best_divisions``).
SEMITONES_PER_OCTAVE = 12

## Cents subdivide a semitone into 100, so an octave is 1200.
CENTS_PER_OCTAVE = 1200.0

NOTE_NAMES: tuple[str, ...] = (
    "C",
    "C#",
    "D",
    "D#",
    "E",
    "F",
    "F#",
    "G",
    "G#",
    "A",
    "A#",
    "B",
)

## Flat spellings map onto the sharp above the note below them.
_FLAT_TO_SHARP = {"Db": "C#", "Eb": "D#", "Gb": "F#", "Ab": "G#", "Bb": "A#"}

## MIDI octave numbering puts C4 (middle C) at 60, so octave 0 starts at 12.
_OCTAVE_OFFSET = 1


def semitone_ratio(semitones: float) -> float:
    """Frequency multiplier for a distance in semitones (2 ** (n / 12))."""
    return float(2.0 ** (semitones / SEMITONES_PER_OCTAVE))


def midi_to_hz(midi: float) -> float:
    """Frequency of a MIDI note: 440 * 2 ** ((n - 69) / 12)."""
    return A4_HZ * semitone_ratio(midi - A4_MIDI)


def hz_to_midi(hz: float) -> float:
    """Fractional MIDI number of a frequency (the inverse of ``midi_to_hz``)."""
    if hz <= 0.0:
        msg = f"frequency must be positive, got {hz}"
        raise ValueError(msg)
    return A4_MIDI + SEMITONES_PER_OCTAVE * math.log2(hz / A4_HZ)


def cents(ratio: float) -> float:
    """Size of a frequency ratio in cents (1200 per octave)."""
    if ratio <= 0.0:
        msg = f"ratio must be positive, got {ratio}"
        raise ValueError(msg)
    return CENTS_PER_OCTAVE * math.log2(ratio)


def note_name(midi: int) -> str:
    """Scientific pitch name of a MIDI note, e.g. 69 -> "A4"."""
    octave, index = divmod(midi, SEMITONES_PER_OCTAVE)
    return f"{NOTE_NAMES[index]}{octave - _OCTAVE_OFFSET}"


def parse_note(name: str) -> int:
    """MIDI number of a note name such as "A4", "C#3" or "Bb2"."""
    letters = name.rstrip("-0123456789")
    digits = name[len(letters) :]
    if not letters or not digits:
        msg = f"not a note name: {name!r}"
        raise ValueError(msg)
    letters = _FLAT_TO_SHARP.get(letters, letters)
    if letters not in NOTE_NAMES:
        msg = f"unknown pitch class in {name!r}"
        raise ValueError(msg)
    octave = int(digits)
    return (octave + _OCTAVE_OFFSET) * SEMITONES_PER_OCTAVE + NOTE_NAMES.index(letters)


def transpose(midis: Sequence[int], semitones: int) -> list[int]:
    """Shift every note by a constant (article section 8: transposition)."""
    return [midi + semitones for midi in midis]


def pitch_class(midi: int) -> int:
    """The note within the octave, 0 (C) to 11 (B)."""
    return midi % SEMITONES_PER_OCTAVE
