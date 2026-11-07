# Copyright (c) 2026 Krzysztof Rudnicki
from typing import cast

import numpy as np
import pytest

from music_theory import analysis, sequencer, synth


def test_beat_seconds() -> None:
    assert sequencer.beat_seconds(120.0) == 0.5
    with pytest.raises(ValueError, match="tempo"):
        sequencer.beat_seconds(0.0)


def test_loop_frames_floors() -> None:
    assert sequencer.loop_frames(120.0, 4.0, 22050) == 44100
    assert sequencer.loop_frames(100.0, 1.0, 22050) == 13230


def test_render_is_exactly_the_requested_length() -> None:
    events = sequencer.sequence([69, 69, 69], 1.0)
    out = sequencer.render(events, 120.0, 4.0, 1000)
    assert len(out) == 2000


def test_render_clips_notes_past_the_end_and_skips_late_starts() -> None:
    late = sequencer.NoteEvent(69, 10.0, 1.0)
    overrun = sequencer.NoteEvent(69, 1.5, 4.0)
    out = sequencer.render([late, overrun], 120.0, 2.0, 1000)
    assert len(out) == 1000
    assert np.any(out[800:])


def test_render_note_applies_velocity_and_detune() -> None:
    quiet = sequencer.render_note(sequencer.NoteEvent(69, 0.0, 1.0, 0.5), 60.0, 22050)
    loud = sequencer.render_note(sequencer.NoteEvent(69, 0.0, 1.0, 1.0), 60.0, 22050)
    assert analysis.peak(quiet) == pytest.approx(analysis.peak(loud) / 2)
    up = sequencer.render_note(
        sequencer.NoteEvent(69, 0.0, 1.0, cents=1200.0), 60.0, 22050
    )
    assert analysis.dominant_frequency(up) == pytest.approx(880.0, abs=1.0)


def test_stack_shares_the_level_between_notes() -> None:
    chord = sequencer.stack([60, 64, 67], 0.0, 1.0, "saw", synth.Envelope())
    assert all(e.velocity == pytest.approx(1 / 3) for e in chord)
    assert sequencer.stack([], 0.0, 1.0) == []


def test_sequence_lays_notes_end_to_end() -> None:
    events = sequencer.sequence([60, 62], 0.5)
    assert [e.start_beat for e in events] == [0.0, 0.5]


@pytest.mark.parametrize(
    ("text", "beats"), [("4/4", 4.0), ("3/4", 3.0), ("6/8", 3.0), ("2/2", 4.0)]
)
def test_meter_beats_per_bar_counts_quarter_notes(text: str, beats: float) -> None:
    meter = sequencer.Meter.parse(text)
    assert meter.beats_per_bar == beats
    assert str(meter) == text


def test_meter_default_is_the_old_fixed_four() -> None:
    assert sequencer.Meter().beats_per_bar == sequencer.BEATS_PER_BAR


@pytest.mark.parametrize("text", ["7/3", "0/4", "3", "a/4", "3/4/4"])
def test_meter_rejects_what_is_not_a_meter(text: str) -> None:
    with pytest.raises(ValueError, match="meter"):
        sequencer.Meter.parse(text)


def test_render_hits_is_exactly_the_requested_length_and_seeded() -> None:
    hits = [
        sequencer.DrumHit("kick", 0.0, 0.5),
        sequencer.DrumHit("hat", 1.0, 0.5, 0.5),
        sequencer.DrumHit("snare", 1.5, 4.0),
        sequencer.DrumHit("kick", 9.0, 0.5),
    ]
    out = sequencer.render_hits(hits, 120.0, 2.0, 1000, (3, 0))
    assert len(out) == 1000
    assert np.any(out[:250])
    assert np.any(out[800:])
    same = sequencer.render_hits(hits, 120.0, 2.0, 1000, (3, 0))
    assert np.array_equal(out, same)
    other = sequencer.render_hits(hits, 120.0, 2.0, 1000, (4, 0))
    assert not np.array_equal(out, other)


def test_drum_kinds_differ_in_brightness_and_fade_to_silence() -> None:
    def centroid(kind: sequencer.DrumKind) -> float:
        sample = sequencer.drum_sample(kind, 4000, np.random.default_rng(1), 22050)
        assert sample[-1] == 0.0
        assert analysis.peak(sample) == pytest.approx(1.0)
        return analysis.spectral_centroid(sample)

    assert centroid("kick") < centroid("snare") < centroid("hat")
    cowbell = cast("sequencer.DrumKind", "cowbell")
    with pytest.raises(ValueError, match="drum"):
        sequencer.drum_sample(cowbell, 100, np.random.default_rng(1))
