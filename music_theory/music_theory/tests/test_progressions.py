# Copyright (c) 2026 Krzysztof Rudnicki
import pytest

from music_theory import progressions, scales

MAJOR = scales.STEP_PATTERNS["major"]


def test_named_lookup_is_case_insensitive() -> None:
    assert progressions.named("POP") == (1, 5, 6, 4)


def test_named_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unknown progression"):
        progressions.named("prog rock")


def test_chords_for_resolves_degrees() -> None:
    prog = progressions.chords_for(60, MAJOR, (1, 5, 6, 4))
    assert progressions.numerals(prog) == "I V vi IV"
    assert prog[1].notes == (67, 71, 74)
    assert prog[2].degree == 6


def test_chords_for_rejects_out_of_range_degree() -> None:
    with pytest.raises(ValueError, match="outside"):
        progressions.chords_for(60, MAJOR, (8,))
    with pytest.raises(ValueError, match="outside"):
        progressions.chords_for(60, MAJOR, (0,))


def test_transpose_adds_a_constant_to_every_note() -> None:
    prog = progressions.chords_for(60, MAJOR, (1, 4))
    moved = progressions.transpose(prog, 4)
    assert moved[0].notes == (64, 68, 71)
    assert moved[1].numeral == "IV"
