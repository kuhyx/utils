# Copyright (c) 2026 Krzysztof Rudnicki
"""Progressions: chord sequences addressed by scale degree, not by note.

Article section 8. Roman numerals are RELATIVE addressing: "I V vi IV" is
the same progression in every key, and transposing is adding one constant to
every MIDI number. Degrees here are 1-based as musicians write them.
"""

from __future__ import annotations

from dataclasses import dataclass

from music_theory import chords, scales

Degrees = tuple[int, ...]

## Progressions the article names, 1-based degrees.
NAMED: dict[str, Degrees] = {
    "pop": (1, 5, 6, 4),
    "jazz": (2, 5, 1),
    "axis": (6, 4, 1, 5),
    "fifties": (1, 6, 4, 5),
    "article": (1, 6, 3, 7),
}


@dataclass(frozen=True)
class ProgressionChord:
    """A chord of a progression: its 1-based degree, numeral and notes."""

    degree: int
    numeral: str
    notes: tuple[int, ...]


def named(name: str) -> Degrees:
    """Degrees of a named progression, e.g. "pop" -> (1, 5, 6, 4)."""
    key = name.lower()
    if key not in NAMED:
        msg = f"unknown progression {name!r}; choose one of {tuple(NAMED)}"
        raise ValueError(msg)
    return NAMED[key]


def chords_for(
    root_midi: int, pattern: scales.StepPattern, degrees: Degrees
) -> list[ProgressionChord]:
    """Resolve 1-based degrees into the diatonic chords of a key."""
    table = chords.diatonic_chords(root_midi, pattern)
    result = []
    for degree in degrees:
        if not 1 <= degree <= len(table):
            msg = f"degree {degree} is outside 1..{len(table)}"
            raise ValueError(msg)
        entry = table[degree - 1]
        result.append(ProgressionChord(degree, entry.numeral, entry.notes))
    return result


def transpose(
    progression: list[ProgressionChord], semitones: int
) -> list[ProgressionChord]:
    """The same progression in another key: add a constant to every note."""
    return [
        ProgressionChord(c.degree, c.numeral, tuple(n + semitones for n in c.notes))
        for c in progression
    ]


def numerals(progression: list[ProgressionChord]) -> str:
    """Human-readable numeral string, e.g. "I V vi IV"."""
    return " ".join(c.numeral for c in progression)
