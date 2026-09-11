# Copyright (c) 2026 Krzysztof Rudnicki
"""Chords: scale notes stacked in thirds, and why V wants to become I.

Article sections 7 and 9. A chord is every other note of the scale from a
starting degree, which stacks harmonics that already share overtones. The
whole difference between a major and a minor triad is one array element
([0, 4, 7] against [0, 3, 7]). The dominant seventh holds both the leading
tone and a tritone, and both resolve by a single semitone into the tonic.
"""

from __future__ import annotations

from dataclasses import dataclass

from music_theory import scales
from music_theory.pitch import SEMITONES_PER_OCTAVE

Intervals = tuple[int, ...]

## Semitone offsets of each chord quality from its root.
QUALITIES: dict[str, Intervals] = {
    "major": (0, 4, 7),
    "minor": (0, 3, 7),
    "diminished": (0, 3, 6),
    "augmented": (0, 4, 8),
    "major7": (0, 4, 7, 11),
    "minor7": (0, 3, 7, 10),
    "dominant7": (0, 4, 7, 10),
    "half-diminished7": (0, 3, 6, 10),
}

## Roman numerals per scale degree; case and the ° come from the quality.
_NUMERALS: tuple[str, ...] = ("I", "II", "III", "IV", "V", "VI", "VII")

## Interval sizes the ear cares about here.
TRITONE = 6
SEMITONE = 1
_FIFTH_DEGREE = 4
_TRIAD_SIZE = 3


@dataclass(frozen=True)
class DiatonicChord:
    """One chord built on a scale degree, with its Roman numeral address."""

    degree: int
    numeral: str
    quality: str
    notes: tuple[int, ...]


def chord(root_midi: int, quality: str) -> list[int]:
    """MIDI notes of a chord of the given quality on a root."""
    if quality not in QUALITIES:
        msg = f"unknown chord quality {quality!r}"
        raise ValueError(msg)
    return [root_midi + offset for offset in QUALITIES[quality]]


def quality_of(notes: list[int]) -> str | None:
    """Name of the quality whose intervals match these notes, if any."""
    if not notes:
        return None
    intervals = tuple(note - notes[0] for note in notes)
    for name, shape in QUALITIES.items():
        if shape == intervals:
            return name
    return None


def stacked_thirds(
    root_midi: int, pattern: scales.StepPattern, degree: int, size: int = _TRIAD_SIZE
) -> list[int]:
    """Every other scale note from ``degree``: the chord on that degree."""
    return [
        scales.pitch_at_degree(root_midi, pattern, degree + 2 * i) for i in range(size)
    ]


def roman(degree: int, quality: str) -> str:
    """Roman numeral for a 0-based degree: upper case major, lower minor, ° dim."""
    numeral = _NUMERALS[degree % len(_NUMERALS)]
    if quality in {"minor", "minor7"}:
        return numeral.lower()
    if quality in {"diminished", "half-diminished7"}:
        return numeral.lower() + "°"
    if quality == "augmented":
        return numeral + "+"
    return numeral


def diatonic_chords(
    root_midi: int, pattern: scales.StepPattern, size: int = _TRIAD_SIZE
) -> list[DiatonicChord]:
    """The chord on every degree of the scale (C major: C Dm Em F G Am B°)."""
    result = []
    for degree in range(len(pattern)):
        notes = stacked_thirds(root_midi, pattern, degree, size)
        quality = quality_of(notes) or "other"
        result.append(
            DiatonicChord(degree, roman(degree, quality), quality, tuple(notes))
        )
    return result


def dominant_seventh(key_root: int, pattern: scales.StepPattern) -> list[int]:
    """The V7 chord of a key: the fifth degree with a minor seventh on top."""
    fifth = scales.pitch_at_degree(key_root, pattern, _FIFTH_DEGREE)
    return chord(fifth, "dominant7")


def tritone_pair(notes: list[int]) -> tuple[int, int] | None:
    """The two notes six semitones apart, if the chord contains a tritone."""
    for i, low in enumerate(notes):
        for high in notes[i + 1 :]:
            if (high - low) % SEMITONES_PER_OCTAVE == TRITONE:
                return (low, high)
    return None


def resolution(key_root: int, pattern: scales.StepPattern) -> list[tuple[int, int]]:
    """How each tense note of V7 moves into I, as (from, to) pairs.

    In C: B (the leading tone) rises to C and F (the seventh) falls to E.
    Together they are the tritone collapsing by contrary semitones into a
    stable major third -- the strongest pull in Western harmony.
    """
    seventh = dominant_seventh(key_root, pattern)
    tonic = stacked_thirds(key_root, pattern, 0)
    # The tonic in every nearby octave, so B4 finds C5 and F5 finds E5.
    targets = [
        t + o for t in tonic for o in (-SEMITONES_PER_OCTAVE, 0, SEMITONES_PER_OCTAVE)
    ]
    moves = []
    for note in seventh:
        close = [t for t in targets if abs(t - note) == SEMITONE]
        if close:
            moves.append((note, close[0]))
    return moves
