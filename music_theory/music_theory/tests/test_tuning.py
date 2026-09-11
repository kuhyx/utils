# Copyright (c) 2026 Krzysztof Rudnicki
from fractions import Fraction

import pytest

from music_theory import tuning


def test_harmonic_series_multiplies() -> None:
    assert tuning.harmonic_series(100.0, 4) == [100.0, 200.0, 300.0, 400.0]


def test_repeat_cycles_is_the_denominator() -> None:
    assert tuning.repeat_cycles(Fraction(3, 2)) == 2
    assert tuning.repeat_cycles(tuning.JUST_RATIOS["minor second"]) == 15


def test_pythagorean_comma_value() -> None:
    assert tuning.pythagorean_comma() == pytest.approx(1.0136432647705078)


def test_stack_fifths_folds_into_the_octave() -> None:
    assert tuning.stack_fifths(0) == 1.0
    folded = tuning.stack_fifths(12)
    assert folded >= 1.0
    assert folded < 2.0
    assert tuning.stack_fifths(12) == pytest.approx(tuning.pythagorean_comma())


def test_tempered_fifth_error_is_about_a_tenth_of_a_percent() -> None:
    score = tuning.fifth_error(12)
    assert score.step == 7
    assert score.ratio == pytest.approx(1.498307, abs=1e-6)
    assert score.error == pytest.approx(0.00113, abs=1e-5)


def test_fifth_error_rejects_non_positive() -> None:
    with pytest.raises(ValueError, match="positive"):
        tuning.fifth_error(0)


def test_twelve_is_the_first_acceptable_division() -> None:
    assert tuning.first_acceptable_division(25) == 12


def test_no_acceptable_division_below_twelve() -> None:
    assert tuning.first_acceptable_division(11) is None


def test_best_divisions_is_sorted_by_error() -> None:
    scores = tuning.best_divisions(25)
    errors = [s.error for s in scores]
    assert errors == sorted(errors)
    assert len(scores) == 25
    small = [s.divisions for s in scores if s.divisions <= 12]
    assert small[0] == 12


def test_beat_frequency_is_the_difference() -> None:
    assert tuning.beat_frequency(440.0, 446.0) == pytest.approx(6.0)
    assert tuning.beat_frequency(446.0, 440.0) == pytest.approx(6.0)


def test_tritone_ratio_is_root_two() -> None:
    assert pytest.approx(2.0) == tuning.TRITONE_RATIO**2
