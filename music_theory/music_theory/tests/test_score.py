# Copyright (c) 2026 Krzysztof Rudnicki
from pathlib import Path

import numpy as np
import pytest

from music_theory import analysis, compose, score, score_events, sequencer

## 120 bpm at 22050 Hz is 11025 frames a beat: every bar starts on a whole
## frame, so a section rendered alone lines up sample for sample.
WALTZ = """\
# a test waltz
title test waltz
meter 3/4
tempo 120
seed 7
voice lead wave=sine vel=0.5
voice bass wave=sine vel=0.9
voice drums noise vel=0.4
section A bars=2
lead: A4/3 | A4/2 -/1
bass: A2/3 |
bass: A2/1.5 A2/1.5
drums: k . h . h . | k . s . h .
section B bars=1
lead: E5/1 E5/1 E5/1
drums: k h h h s h
"""


def _render(text: str) -> np.ndarray:
    return score_events.render(score.parse(text))


def _drop(text: str, prefix: str) -> str:
    return "".join(
        line for line in text.splitlines(keepends=True) if not line.startswith(prefix)
    )


def test_parse_reads_header_voices_sections_and_default_order() -> None:
    piece = score.parse(WALTZ)
    assert piece.title == "test waltz"
    assert str(piece.meter) == "3/4"
    assert piece.tempo_bpm == 120.0
    assert piece.seed == 7
    assert piece.sample_rate == 22050
    assert [v.name for v in piece.voices] == ["lead", "bass", "drums"]
    assert [v.noise for v in piece.voices] == [False, False, True]
    assert piece.order == ("A", "B")
    assert score_events.length_beats(piece) == 9.0
    assert piece.to_dict() == {"format": "score", "title": "test waltz", "text": WALTZ}


def test_header_defaults_and_rate() -> None:
    piece = score.parse("rate 8000\nvoice v\nsection A bars=1\nv: C4/4\n")
    assert (piece.meter.beats_per_bar, piece.tempo_bpm, piece.seed) == (4.0, 120.0, 0)
    assert piece.sample_rate == 8000
    assert piece.voices[0].waveform == "triangle"


def test_note_events_follow_the_bars_and_skip_rests() -> None:
    events = score_events.note_events(score.parse(WALTZ))
    lead = [(e.midi, e.start_beat, e.length_beats) for e in events if e.velocity == 0.5]
    assert lead == [(69, 0.0, 3.0), (69, 3.0, 2.0), (76, 6.0, 1.0), (76, 7.0, 1.0),
                    (76, 8.0, 1.0)]  # fmt: skip


@pytest.mark.parametrize(("meter", "frames"), [("3/4", 3), ("6/8", 3), ("4/4", 4)])
def test_meter_renders_bar_exact_loops(meter: str, frames: int) -> None:
    text = f"meter {meter}\ntempo 100\nvoice d noise\nsection A bars=4\n"
    signal = compose.compose_score(score.parse(text))
    assert len(signal) == sequencer.loop_frames(100.0, 4 * frames)
    assert not np.any(signal)


def test_six_eight_drums_take_six_eighths_a_bar() -> None:
    text = "meter 6/8\nvoice d noise\nsection A bars=1\nd: k . . s . .\n"
    hits = score_events.drum_parts(score.parse(text))
    assert hits == [(0, [sequencer.DrumHit("kick", 0.0, 0.5, 0.5),
                         sequencer.DrumHit("snare", 1.5, 0.5, 0.5)])]  # fmt: skip


def test_waltz_is_bar_exact_normalised_and_byte_identical() -> None:
    signal = compose.compose_score(score.parse(WALTZ))
    assert len(signal) == sequencer.loop_frames(120.0, 9.0)
    assert analysis.peak(signal) == pytest.approx(0.8)
    assert np.array_equal(signal, compose.compose_score(score.parse(WALTZ)))


def test_two_named_voices_stack() -> None:
    no_drums = _drop(WALTZ, "drums:")
    both = _render(no_drums)
    lead = _render(_drop(no_drums, "bass:"))
    bass = _render(_drop(no_drums, "lead:"))
    assert np.allclose(both, lead + bass)
    assert not np.array_equal(both, lead)
    assert analysis.dominant_frequency(lead) == pytest.approx(440.0, abs=1.0)
    assert analysis.dominant_frequency(bass) == pytest.approx(110.0, abs=1.0)


def test_noise_drums_are_seeded_bright_and_not_silent() -> None:
    drums_only = _drop(_drop(WALTZ, "lead:"), "bass:")
    first = _render(drums_only)
    assert np.any(first)
    assert np.array_equal(first, _render(drums_only))
    assert not np.array_equal(first, _render(drums_only.replace("seed 7", "seed 8")))
    pitched = _render(_drop(WALTZ, "drums:"))
    full = _render(WALTZ)
    assert analysis.spectral_centroid(full) > analysis.spectral_centroid(pitched)
    assert analysis.dominant_frequency(full) == pytest.approx(
        analysis.dominant_frequency(pitched), abs=1.0
    )


def test_play_order_renders_sections_in_sequence() -> None:
    a_then_b = _render(WALTZ + "play A B\n")
    a_only = _render(WALTZ + "play A\n")
    b_only = _render(WALTZ + "play B\n")
    assert np.array_equal(a_then_b, np.concatenate([a_only, b_only]))
    assert np.array_equal(_render(WALTZ), a_then_b)
    assert np.array_equal(
        _render(WALTZ + "play B A\n"), np.concatenate([b_only, a_only])
    )
    repeated = score.parse(WALTZ + "play A B A\n")
    assert score_events.length_beats(repeated) == 15.0


@pytest.mark.parametrize(
    ("text", "match"),
    [
        (
            "voice v\nsection A bars=1\nv: C4/5\n",
            "line 3: voice v bar 1: expected 4 beats, got 5",
        ),
        (
            "meter 3/4\nvoice v\nsection A bars=1\nv: C4/2 D4/3\n",
            "expected 3 beats, got 5",
        ),
        ("voice d noise\nsection A bars=1\nd: k . .\n", "expected 4 beats, got 1.5"),
        ("voice v\nsection A bars=1\nw: C4/4\n", "line 3: unknown voice 'w'"),
        ("meter 7/3\n", "line 1: .*meter"),
        ("voice v\n", "no sections"),
        ("voice v\nsection A bars=1\nplay A C\n", "line 3: unknown section 'C'"),
        (
            "voice v\nsection A bars=2\nv: C4/4\n",
            "line 2: section A: voice v has 1 bars, expected 2",
        ),
        (
            (
                "voice v\nsection A bars=1\nsection B bars=1\nv: C4/4 |\n"
                "section A bars=1\n"
            ),
            "line 5: duplicate section 'A'",
        ),
        ("voice v\nvoice v\n", "line 2: duplicate voice 'v'"),
        ("v: C4/4\n", "line 1: part outside a section"),
        ("section A bars=1\nmeter 3/4\n", "line 2: meter must come before"),
        ("voice v\nsection A bars=1\nv: H4/4\n", "line 3: .*H4"),
        ("voice v\nsection A bars=1\nv: C4/x\n", "line 3: .*length"),
        ("voice v\nsection A bars=1\nv: C4/0\n", "line 3: .*length"),
        ("voice d noise\nsection A bars=1\nd: k x . . . . . .\n", "drum step 'x'"),
        ("voice v wave=organ\n", "line 1: unknown waveform"),
        ("voice v loud=1\n", "line 1: unknown voice option"),
        ("voice d noise wave=saw\n", "line 1: a noise voice"),
        ("voice\n", "line 1: voice needs a name"),
        ("voice v vel=x\n", "line 1: .*number"),
        ("tempo 0\n", "line 1: tempo"),
        ("seed -1\n", "line 1: seed"),
        ("seed 1.5\n", "line 1: .*integer"),
        ("section A\n", "line 1: section needs"),
        ("section A bars=0\n", "line 1: .*bars"),
        ("swing 60\n", "line 1: unknown directive 'swing'"),
        ("play\n", "line 1: play needs"),
    ],
)
def test_parse_errors_name_the_line(text: str, match: str) -> None:
    with pytest.raises(score.ScoreError, match=match):
        score.parse(text)


EXAMPLES = Path(__file__).parents[2] / "examples"


@pytest.mark.parametrize(
    ("name", "meter", "bars", "hz"),
    [("waltz", "3/4", 16, 130.81), ("jig", "6/8", 16, 98.0)],
)
def test_examples_render_bar_exact_at_their_stated_pitch(
    name: str, meter: str, bars: int, hz: float
) -> None:
    piece = score.parse((EXAMPLES / f"{name}.txt").read_text())
    signal = compose.compose_score(piece)
    assert str(piece.meter) == meter
    assert len(signal) == sequencer.loop_frames(piece.tempo_bpm, bars * 3.0)
    assert analysis.dominant_frequency(signal) == pytest.approx(hz, abs=1.0)
