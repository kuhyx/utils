# Copyright (c) 2026 Krzysztof Rudnicki
import numpy as np
import pytest

from music_theory import envelopes

RATE = 1000


def test_exponential_has_a_constant_ratio_per_time_constant() -> None:
    gain = envelopes.exponential(500, 0.1, RATE)
    assert gain[0] == 1.0
    ratios = gain[100:400:100] / gain[0:300:100]
    assert ratios.tolist() == pytest.approx([np.exp(-1.0)] * 3)


def test_exponential_rejects_a_non_positive_time_constant() -> None:
    with pytest.raises(ValueError, match="time constant"):
        envelopes.exponential(10, 0.0, RATE)


def test_shape_length_is_attack_hold_decay() -> None:
    env = envelopes.Shape(attack=0.01, hold=0.02, decay=0.07)
    assert env.seconds == pytest.approx(0.1)
    assert len(envelopes.shape(env, RATE)) == 100


def test_shape_rises_holds_and_dies_without_a_click() -> None:
    gain = envelopes.shape(envelopes.Shape(attack=0.01, hold=0.02, decay=0.1), RATE)
    assert gain[0] == 0.0
    assert gain[10:30].tolist() == pytest.approx([1.0] * 20)
    tail = gain[30:]
    assert np.all(np.diff(tail) <= 0.0)
    assert tail[-1] < 0.01
    assert float(np.min(gain)) >= 0.0


def test_punch_boosts_the_start_of_the_hold() -> None:
    gain = envelopes.shape(
        envelopes.Shape(attack=0.0, hold=0.05, punch=0.5, decay=0.05), RATE
    )
    assert gain[0] == pytest.approx(1.5)
    assert gain[49] == pytest.approx(1.0, abs=0.02)
    assert float(np.max(gain)) == pytest.approx(1.5)


def test_steeper_curve_decays_faster() -> None:
    soft = envelopes.shape(envelopes.Shape(attack=0.0, hold=0.0, decay=0.1), RATE)
    hard = envelopes.shape(
        envelopes.Shape(attack=0.0, hold=0.0, decay=0.1, curve=10.0), RATE
    )
    assert hard[50] < soft[50]
    assert hard[0] == soft[0] == 1.0


def test_shape_of_nothing_is_empty() -> None:
    zero = envelopes.Shape(attack=0.0, hold=0.0, decay=0.0)
    assert envelopes.shape(zero, RATE).size == 0
