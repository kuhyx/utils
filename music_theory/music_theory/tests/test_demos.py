# Copyright (c) 2026 Krzysztof Rudnicki
import numpy as np
import pytest

from music_theory import analysis, demo_support, demos, synth


def test_registry_covers_every_section_in_order() -> None:
    names = list(demos.REGISTRY)
    assert names[0] == "tone"
    assert names[-1] == "bracket"
    assert len(names) == 17


@pytest.mark.parametrize("name", list(demos.REGISTRY))
def test_every_demo_renders_audio_with_facts(name: str) -> None:
    demo = demos.run(name)
    assert demo.name == name
    assert demo.facts
    assert demo.signal.size > 0
    assert analysis.peak(demo.signal) == pytest.approx(synth.DEFAULT_PEAK)
    assert np.isfinite(demo.signal).all()


def test_run_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="unknown demo"):
        demos.run("silence")


def test_selected_expands_all_and_validates() -> None:
    assert demos.selected("all") == list(demos.REGISTRY)
    assert demos.selected("comma") == ["comma"]
    with pytest.raises(ValueError, match="unknown demo"):
        demos.selected("nope")


def test_tone_demo_peaks_at_440() -> None:
    demo = demos.run("tone")
    assert analysis.dominant_frequency(demo.signal) == pytest.approx(440.0, abs=1.0)


def test_resolution_demo_names_both_semitone_moves() -> None:
    facts = demos.run("resolution").facts
    assert "B4 -> C5 by one semitone" in facts
    assert "F5 -> E5 by one semitone" in facts


def test_divisions_demo_answers_twelve() -> None:
    assert any(fact.endswith(": 12") for fact in demos.run("divisions").facts)


def test_bracket_demo_is_darker_second() -> None:
    facts = demos.run("bracket").facts
    clean = float(facts[0].rsplit(" ", 2)[1])
    ruined = float(facts[1].rsplit(" ", 2)[1])
    assert ruined < clean


def test_support_helpers() -> None:
    line = demo_support.tones([220.0, 440.0], 0.1)
    assert line.size > 2 * int(0.1 * synth.SAMPLE_RATE)
    both = demo_support.pair(220.0, 330.0, 0.1)
    assert analysis.peak(both) == pytest.approx(synth.DEFAULT_PEAK)
    assert demo_support.names([60, 69]) == "C4 A4"
    assert demo_support.chord_line([[60, 64, 67]], 1.0).size > 0
    assert demo_support.note_line([60, 62], 0.5).size > 0
