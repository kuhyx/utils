# Copyright (c) 2026 Krzysztof Rudnicki
"""Demos for article sections 6-11: scales, chords, keys, resolution, the piece."""

from __future__ import annotations

import numpy as np

from music_theory import (
    analysis,
    chords,
    compose,
    pitch,
    progressions,
    scales,
    synth,
    wav,
)
from music_theory.demo_support import Demo, chord_line, names, note_line

_C4 = 60
_E_MAJOR_SHIFT = 4
_TRIAD_QUALITIES = ("major", "minor", "diminished", "augmented")
_SEVENTH_QUALITIES = ("major7", "minor7", "dominant7")
_HALF_SECOND_FRAMES = synth.SAMPLE_RATE // 2
_THIRD_INDEX = 1
_SEVENTH_INDEX = 3


def scale_demo() -> Demo:
    """Section 6: a scale is a step array folded from a root."""
    major = scales.build(_C4, scales.STEP_PATTERNS["major"])
    minor = scales.build(pitch.parse_note("A3"), scales.STEP_PATTERNS["minor"])
    return Demo(
        "scale",
        "6 scales",
        (
            f"major steps {scales.STEP_PATTERNS['major']} from C4 -> {major}",
            f"that is {names(major)}",
            f"minor steps {scales.STEP_PATTERNS['minor']} from A3 -> {names(minor)}",
        ),
        note_line(major + minor),
    )


def modes_demo() -> Demo:
    """Section 6: all seven modes are the same array rotated."""
    lines: list[int] = []
    facts = []
    for index, name in enumerate(scales.MODE_NAMES):
        pattern = scales.mode(name)
        facts.append(f"{name:10s} = major rotated {index}: {pattern}")
        lines += scales.build(_C4, pattern)
    facts.append("ionian is the major scale, aeolian (rotation 5) the natural minor")
    return Demo("modes", "6 modes", tuple(facts), note_line(lines, 0.25))


def chords_demo() -> Demo:
    """Section 7: one array element is the whole major/minor difference."""
    qualities = (*_TRIAD_QUALITIES, *_SEVENTH_QUALITIES)
    stacks = [chords.chord(_C4, q) for q in qualities]
    facts = tuple(
        f"{q:11s} {chords.QUALITIES[q]} -> {names(s)}"
        for q, s in zip(qualities, stacks, strict=True)
    )
    return Demo("chords", "7 chord qualities", facts, chord_line(stacks, 1.5))


def diatonic_demo() -> Demo:
    """Section 8: the seven chords that live inside one key."""
    table = chords.diatonic_chords(_C4, scales.STEP_PATTERNS["major"])
    facts = tuple(
        f"{c.numeral:4s} {c.quality:10s} {names(list(c.notes))}" for c in table
    )
    return Demo(
        "diatonic", "8 keys", facts, chord_line([list(c.notes) for c in table], 1.0)
    )


def transpose_demo() -> Demo:
    """Section 8: the same numerals in two keys differ by one constant."""
    pattern = scales.STEP_PATTERNS["major"]
    in_c = progressions.chords_for(_C4, pattern, progressions.named("pop"))
    in_e = progressions.transpose(in_c, _E_MAJOR_SHIFT)
    both = [list(c.notes) for c in in_c] + [list(c.notes) for c in in_e]
    return Demo(
        "transpose",
        "8 transposition",
        (
            f"{progressions.numerals(in_c)} in C: {_names_of(in_c)}",
            f"add {_E_MAJOR_SHIFT} to every note -> in E: {_names_of(in_e)}",
        ),
        chord_line(both, 1.0),
    )


def _names_of(prog: list[progressions.ProgressionChord]) -> list[str]:
    return [names(list(c.notes)) for c in prog]


def resolution_demo() -> Demo:
    """Section 9: V7 pulls into I through a leading tone and a tritone."""
    pattern = scales.STEP_PATTERNS["major"]
    seventh = chords.dominant_seventh(_C4, pattern)
    tonic = chords.stacked_thirds(_C4, pattern, 0)
    # The third and the seventh of any dominant seventh are a tritone apart.
    tritone = [seventh[_THIRD_INDEX], seventh[_SEVENTH_INDEX]]
    moves = chords.resolution(_C4, pattern)
    facts = [f"V7 in C = {names(seventh)}"]
    facts.append(f"tritone inside it: {names(tritone)} (six semitones apart)")
    facts += [
        f"{pitch.note_name(a)} -> {pitch.note_name(b)} by one semitone"
        for a, b in moves
    ]
    return Demo(
        "resolution",
        "9 tension and resolution",
        tuple(facts),
        chord_line([seventh, tonic], 2.0),
    )


def progressions_demo() -> Demo:
    """Section 9: the loops everyone has heard."""
    pattern = scales.STEP_PATTERNS["major"]
    facts = []
    lines: list[list[int]] = []
    for name in ("pop", "jazz", "axis", "fifties"):
        prog = progressions.chords_for(_C4, pattern, progressions.named(name))
        facts.append(f"{name:8s} {progressions.numerals(prog)}")
        lines += [list(c.notes) for c in prog]
    return Demo(
        "progressions", "9 common progressions", tuple(facts), chord_line(lines, 1.0)
    )


def piece_demo() -> Demo:
    """Section 11: the whole article in one recipe."""
    recipe = compose.Recipe(bars=4)
    signal = compose.compose(recipe)
    return Demo(
        "piece",
        "11 a complete composition",
        (
            (
                f"key {recipe.key} {recipe.mode}, {recipe.tempo_bpm:.0f} bpm, "
                f"degrees {recipe.progression}"
            ),
            (
                f"bass + arpeggio + seeded melody, "
                f"{wav.duration_seconds(signal):.1f} s, loops on the bar"
            ),
        ),
        signal,
    )


def bracket_demo() -> Demo:
    """Beyond the article: the same piece, then the same piece ruined."""
    clean = compose.Recipe(bars=4, mode="major", tempo_bpm=112.0)
    ruined = compose.with_degrade(clean, 1.0)
    a = compose.compose(clean)
    b = compose.compose(ruined)
    return Demo(
        "bracket",
        "12 degrade (not in the article)",
        (
            (
                f"clean: {compose.effective(clean).mode}, "
                f"centroid {analysis.spectral_centroid(a):.0f} Hz"
            ),
            (
                f"ruined: {compose.effective(ruined).mode}, "
                f"{compose.effective(ruined).tempo_bpm:.0f} bpm, "
                f"centroid {analysis.spectral_centroid(b):.0f} Hz"
            ),
            "same seed, same chords: the ending is the opening, degraded",
        ),
        _join(a, b),
    )


def _join(a: synth.Signal, b: synth.Signal) -> synth.Signal:
    """Two signals with half a second of silence between them."""
    return np.concatenate((a, np.zeros(_HALF_SECOND_FRAMES), b))
