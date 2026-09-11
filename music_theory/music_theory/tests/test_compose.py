# Copyright (c) 2026 Krzysztof Rudnicki
import numpy as np
import pytest

from music_theory import analysis, compose, sequencer


def test_recipe_round_trips_through_dict() -> None:
    recipe = compose.Recipe(key="C4", mode="major", progression=(1, 5, 6, 4), bars=2)
    assert compose.Recipe.from_dict(recipe.to_dict()) == recipe
    assert recipe.to_dict()["progression"] == [1, 5, 6, 4]


def test_recipe_from_partial_dict_uses_defaults() -> None:
    recipe = compose.Recipe.from_dict({"tempo_bpm": 90})
    assert recipe.tempo_bpm == 90.0
    assert recipe.key == compose.Recipe().key


@pytest.mark.parametrize(
    ("data", "match"),
    [
        ({"colour": "blue"}, "unknown recipe keys"),
        ({"key": 3}, "string"),
        ({"tempo_bpm": "fast"}, "number"),
        ({"tempo_bpm": True}, "number"),
        ({"bars": 2.5}, "integer"),
        ({"bars": False}, "integer"),
        ({"progression": "1 5 6 4"}, "list of integers"),
        ({"progression": [1, "5"]}, "integer"),
        ({"waveform": "noise"}, "unknown waveform"),
    ],
)
def test_recipe_rejects_bad_data(data: dict[str, object], match: str) -> None:
    with pytest.raises((ValueError, TypeError), match=match):
        compose.Recipe.from_dict(data)


def test_bass_line_is_one_root_per_bar_an_octave_down() -> None:
    recipe = compose.Recipe(key="C4", mode="major", progression=(1, 5), bars=4)
    bass = compose.bass_line(recipe)
    assert [e.midi for e in bass] == [48, 55, 48, 55]
    assert all(e.length_beats == sequencer.BEATS_PER_BAR for e in bass)


def test_arpeggio_cycles_chord_tones_in_eighths() -> None:
    recipe = compose.Recipe(key="C4", mode="major", progression=(1,), bars=1)
    arp = compose.arpeggio(recipe)
    assert len(arp) == 8
    assert [e.midi for e in arp[:4]] == [60, 64, 67, 64]
    assert arp[1].start_beat == 0.5


def test_melody_is_deterministic_in_scale_and_snaps_bar_starts() -> None:
    recipe = compose.Recipe(key="C4", mode="major", progression=(1, 4), bars=4, seed=7)
    first = compose.melody(recipe)
    assert first == compose.melody(recipe)
    assert first
    for event in first:
        assert (event.midi - 60) % 12 in {0, 2, 4, 5, 7, 9, 11}
    chord_tones = {0, 4, 7, 5, 9}
    for event in first:
        if not event.start_beat % sequencer.BEATS_PER_BAR:
            assert (event.midi - 60) % 12 in chord_tones


def test_melody_thins_out_and_detunes_when_degraded() -> None:
    clean = compose.Recipe(bars=8, seed=3)
    ruined = compose.with_degrade(clean, 1.0)
    assert len(compose.melody(ruined)) < len(compose.melody(clean))
    assert any(e.cents for e in compose.melody(ruined))
    assert not any(e.cents for e in compose.melody(clean))


def test_compose_loops_on_the_bar_and_is_normalised() -> None:
    recipe = compose.Recipe(bars=2, tempo_bpm=120.0)
    signal = compose.compose(recipe)
    assert len(signal) == sequencer.loop_frames(120.0, 8.0)
    assert analysis.peak(signal) == pytest.approx(0.8)
    assert np.array_equal(signal, compose.compose(recipe))


def test_degrade_zero_is_byte_identical_and_full_is_darker() -> None:
    clean = compose.Recipe(bars=2, mode="major")
    assert np.array_equal(
        compose.compose(clean), compose.compose(compose.with_degrade(clean, 0.0))
    )
    ruined = compose.compose(compose.with_degrade(clean, 1.0))
    assert analysis.spectral_centroid(ruined) < analysis.spectral_centroid(
        compose.compose(clean)
    )
    assert compose.effective(compose.with_degrade(clean, 1.0)).mode == "minor"


def test_length_beats() -> None:
    assert compose.length_beats(compose.Recipe(bars=3)) == 12.0
