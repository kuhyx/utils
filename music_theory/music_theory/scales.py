# Copyright (c) 2026 Krzysztof Rudnicki
"""Scales: a subset of the twelve notes, encoded as the gaps between them.

Article section 6. A scale is an array of step sizes that sums to twelve;
the gaps are UNEVEN on purpose, so the ear can tell where in the octave it
is. All seven modes are the same major-scale array rotated, which is why
they are built here by rotation rather than stored as seven tables.
"""

from __future__ import annotations

from music_theory.pitch import SEMITONES_PER_OCTAVE

StepPattern = tuple[int, ...]

## Named step patterns. Every one sums to twelve.
STEP_PATTERNS: dict[str, StepPattern] = {
    "major": (2, 2, 1, 2, 2, 2, 1),
    "minor": (2, 1, 2, 2, 1, 2, 2),
    "harmonic minor": (2, 1, 2, 2, 1, 3, 1),
    "major pentatonic": (2, 2, 3, 2, 3),
    "minor pentatonic": (3, 2, 2, 3, 2),
    "blues": (3, 2, 1, 1, 3, 2),
    "whole tone": (2, 2, 2, 2, 2, 2),
}

## The seven modes are rotations of the major scale, in this order.
MODE_NAMES: tuple[str, ...] = (
    "ionian",
    "dorian",
    "phrygian",
    "lydian",
    "mixolydian",
    "aeolian",
    "locrian",
)

## Rotation indices worth naming: major is rotation 0, natural minor is 5.
MAJOR_ROTATION = 0
MINOR_ROTATION = 5


def validate(pattern: StepPattern) -> StepPattern:
    """Return the pattern if it spans exactly one octave, else raise."""
    if sum(pattern) != SEMITONES_PER_OCTAVE:
        msg = (
            f"step pattern {pattern} sums to {sum(pattern)}, not {SEMITONES_PER_OCTAVE}"
        )
        raise ValueError(msg)
    if any(step <= 0 for step in pattern):
        msg = f"step pattern {pattern} has a non-positive step"
        raise ValueError(msg)
    return pattern


def rotate(pattern: StepPattern, count: int) -> StepPattern:
    """The same pattern started ``count`` steps later (a mode of it)."""
    if not pattern:
        return pattern
    shift = count % len(pattern)
    return pattern[shift:] + pattern[:shift]


def mode(name: str) -> StepPattern:
    """Step pattern of a named mode, derived by rotating the major scale."""
    key = name.lower()
    if key not in MODE_NAMES:
        msg = f"unknown mode {name!r}; choose one of {MODE_NAMES}"
        raise ValueError(msg)
    return rotate(STEP_PATTERNS["major"], MODE_NAMES.index(key))


def pattern_named(name: str) -> StepPattern:
    """Look a pattern up by scale name OR mode name ("minor", "dorian", ...)."""
    key = name.lower()
    if key in STEP_PATTERNS:
        return STEP_PATTERNS[key]
    if key in MODE_NAMES:
        return mode(key)
    msg = f"unknown scale {name!r}"
    raise ValueError(msg)


def offsets(pattern: StepPattern) -> list[int]:
    """Semitone offset of each degree from the root, root included, octave excluded."""
    validate(pattern)
    result = [0]
    for step in pattern[:-1]:
        result.append(result[-1] + step)
    return result


def build(root_midi: int, pattern: StepPattern) -> list[int]:
    """MIDI notes of one octave of the scale, root through to the octave above.

    This is the article's ``reduce`` over the step array: C major from 60
    gives [60, 62, 64, 65, 67, 69, 71, 72].
    """
    validate(pattern)
    notes = [root_midi]
    for step in pattern:
        notes.append(notes[-1] + step)
    return notes


def pitch_at_degree(root_midi: int, pattern: StepPattern, degree: int) -> int:
    """MIDI note of a 0-based scale degree, wrapping across octaves.

    Degree 7 of a seven-note scale is the root an octave up; degree -1 is
    the note just below the root. This is what lets a melody be written as
    degree numbers and moved up or down without leaving the scale.
    """
    steps = offsets(pattern)
    octave, index = divmod(degree, len(steps))
    return root_midi + octave * SEMITONES_PER_OCTAVE + steps[index]


def is_in_scale(root_midi: int, pattern: StepPattern, midi: int) -> bool:
    """Whether a note belongs to the scale (in any octave)."""
    return (midi - root_midi) % SEMITONES_PER_OCTAVE in offsets(pattern)
