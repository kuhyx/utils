# Copyright (c) 2026 Krzysztof Rudnicki
import pytest

from music_theory import chords, scales

MAJOR = scales.STEP_PATTERNS["major"]


def test_major_and_minor_differ_by_one_element() -> None:
    assert chords.chord(60, "major") == [60, 64, 67]
    assert chords.chord(60, "minor") == [60, 63, 67]


def test_chord_rejects_unknown_quality() -> None:
    with pytest.raises(ValueError, match="quality"):
        chords.chord(60, "sus-whatever")


def test_quality_of_inverts_chord() -> None:
    for name in chords.QUALITIES:
        assert chords.quality_of(chords.chord(60, name)) == name
    assert chords.quality_of([]) is None
    assert chords.quality_of([60, 61, 62]) is None


def test_stacked_thirds_builds_the_triad() -> None:
    assert chords.stacked_thirds(60, MAJOR, 0) == [60, 64, 67]
    assert chords.stacked_thirds(60, MAJOR, 4, 4) == [67, 71, 74, 77]


@pytest.mark.parametrize(
    ("degree", "quality", "numeral"),
    [
        (0, "major", "I"),
        (1, "minor", "ii"),
        (6, "diminished", "vii°"),
        (2, "augmented", "III+"),
        (4, "dominant7", "V"),
        (1, "half-diminished7", "ii°"),
        (5, "minor7", "vi"),
    ],
)
def test_roman(degree: int, quality: str, numeral: str) -> None:
    assert chords.roman(degree, quality) == numeral


def test_diatonic_chords_of_c_major() -> None:
    table = chords.diatonic_chords(60, MAJOR)
    assert [c.numeral for c in table] == ["I", "ii", "iii", "IV", "V", "vi", "vii°"]
    assert table[0].notes == (60, 64, 67)
    assert table[6].quality == "diminished"


def test_diatonic_chords_of_an_odd_scale_fall_back_to_other() -> None:
    table = chords.diatonic_chords(60, scales.STEP_PATTERNS["whole tone"])
    assert all(c.quality == "augmented" for c in table)
    blues = chords.diatonic_chords(60, scales.STEP_PATTERNS["blues"])
    assert "other" in {c.quality for c in blues}


def test_dominant_seventh_of_c() -> None:
    assert chords.dominant_seventh(60, MAJOR) == [67, 71, 74, 77]


def test_tritone_pair() -> None:
    assert chords.tritone_pair([67, 71, 74, 77]) == (71, 77)
    assert chords.tritone_pair([60, 64, 67]) is None


def test_resolution_moves_by_contrary_semitones() -> None:
    assert chords.resolution(60, MAJOR) == [(71, 72), (77, 76)]
