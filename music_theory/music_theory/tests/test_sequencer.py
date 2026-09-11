# Copyright (c) 2026 Krzysztof Rudnicki
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
