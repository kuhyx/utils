# Copyright (c) 2026 Krzysztof Rudnicki
import numpy as np
import pytest

from music_theory import analysis, compose, degrade, synth


def test_clamp() -> None:
    assert degrade.clamp(-1.0) == 0.0
    assert degrade.clamp(2.0) == 1.0
    assert degrade.clamp(0.3) == 0.3


def test_darker_mode() -> None:
    assert degrade.darker_mode("major") == "minor"
    assert degrade.darker_mode("Ionian") == "aeolian"
    assert degrade.darker_mode("blues") == "blues"


def test_apply_to_recipe_flips_mode_only_past_threshold() -> None:
    base = compose.Recipe(mode="major", tempo_bpm=100.0)
    mild = degrade.apply_to_recipe(compose.with_degrade(base, 0.2))
    assert mild.mode == "major"
    assert mild.tempo_bpm == pytest.approx(93.0)
    full = degrade.apply_to_recipe(compose.with_degrade(base, 1.0))
    assert full.mode == "minor"
    assert full.tempo_bpm == pytest.approx(65.0)


def test_rest_probability_and_detune() -> None:
    rng = np.random.default_rng(0)
    assert degrade.rest_probability(1.0) == degrade.MAX_REST_PROBABILITY
    assert degrade.detune_cents(0.0, rng) == 0.0
    cents = degrade.detune_cents(1.0, rng)
    assert abs(cents) <= degrade.MAX_DETUNE_CENTS


def test_bitcrush_quantises() -> None:
    out = degrade.bitcrush(np.array([0.123456, -0.5]), 2.0)
    assert list(out) == [0.0, -0.5]


def test_process_zero_is_a_copy_and_full_is_darker() -> None:
    saw = synth.oscillator(220.0, 0.5, "saw")
    same = degrade.process(saw, 0.0, synth.SAMPLE_RATE, 1)
    assert np.array_equal(same, saw)
    assert same is not saw
    ruined = degrade.process(saw, 1.0, synth.SAMPLE_RATE, 1)
    assert analysis.spectral_centroid(ruined) < analysis.spectral_centroid(saw)
