# Copyright (c) 2026 Krzysztof Rudnicki
import pytest

from music_theory import scales


def test_every_pattern_sums_to_twelve() -> None:
    for pattern in scales.STEP_PATTERNS.values():
        assert sum(pattern) == 12


def test_c_major_from_the_article() -> None:
    assert scales.build(60, scales.STEP_PATTERNS["major"]) == [
        60,
        62,
        64,
        65,
        67,
        69,
        71,
        72,
    ]


def test_aeolian_is_major_rotated_five() -> None:
    assert scales.mode("aeolian") == scales.rotate(scales.STEP_PATTERNS["major"], 5)
    assert scales.mode("aeolian") == scales.STEP_PATTERNS["minor"]
    assert scales.mode("Ionian") == scales.STEP_PATTERNS["major"]


def test_rotate_wraps_and_handles_empty() -> None:
    assert scales.rotate((1, 2, 3), 4) == (2, 3, 1)
    assert scales.rotate((), 3) == ()


def test_mode_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unknown mode"):
        scales.mode("klingon")


def test_pattern_named_accepts_scales_and_modes() -> None:
    assert scales.pattern_named("minor") == scales.STEP_PATTERNS["minor"]
    assert scales.pattern_named("dorian") == scales.mode("dorian")
    with pytest.raises(ValueError, match="unknown scale"):
        scales.pattern_named("nope")


def test_validate_rejects_bad_sums_and_steps() -> None:
    with pytest.raises(ValueError, match="sums to"):
        scales.validate((2, 2, 2))
    with pytest.raises(ValueError, match="non-positive"):
        scales.validate((13, -1))


def test_offsets_exclude_the_octave() -> None:
    assert scales.offsets(scales.STEP_PATTERNS["major"]) == [0, 2, 4, 5, 7, 9, 11]


def test_pitch_at_degree_wraps_octaves() -> None:
    major = scales.STEP_PATTERNS["major"]
    assert scales.pitch_at_degree(60, major, 0) == 60
    assert scales.pitch_at_degree(60, major, 7) == 72
    assert scales.pitch_at_degree(60, major, -1) == 59
    assert scales.pitch_at_degree(60, major, 9) == 76


def test_is_in_scale() -> None:
    major = scales.STEP_PATTERNS["major"]
    assert scales.is_in_scale(60, major, 76)
    assert not scales.is_in_scale(60, major, 61)
