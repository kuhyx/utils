# Copyright (c) 2026 Krzysztof Rudnicki
import pytest

from music_theory import pitch


def test_a4_is_440_hz() -> None:
    assert pitch.midi_to_hz(69) == pytest.approx(440.0)


def test_octave_doubles_frequency() -> None:
    assert pitch.midi_to_hz(81) == pytest.approx(880.0)
    assert pitch.midi_to_hz(57) == pytest.approx(220.0)


def test_semitone_ratio_is_twelfth_root_of_two() -> None:
    assert pitch.semitone_ratio(12) == pytest.approx(2.0)
    assert pitch.semitone_ratio(1) == pytest.approx(1.059463, abs=1e-6)


def test_hz_to_midi_round_trips() -> None:
    for midi in (0, 60, 69, 127):
        assert pitch.hz_to_midi(pitch.midi_to_hz(midi)) == pytest.approx(midi)


def test_hz_to_midi_rejects_non_positive() -> None:
    with pytest.raises(ValueError, match="positive"):
        pitch.hz_to_midi(0.0)


def test_cents_of_an_octave_is_1200() -> None:
    assert pitch.cents(2.0) == pytest.approx(1200.0)


def test_cents_rejects_non_positive() -> None:
    with pytest.raises(ValueError, match="positive"):
        pitch.cents(-1.0)


@pytest.mark.parametrize(
    ("midi", "name"), [(60, "C4"), (69, "A4"), (61, "C#4"), (59, "B3"), (12, "C0")]
)
def test_note_name(midi: int, name: str) -> None:
    assert pitch.note_name(midi) == name


@pytest.mark.parametrize(
    ("name", "midi"), [("C4", 60), ("A4", 69), ("C#3", 49), ("Bb3", 58), ("Db-1", 1)]
)
def test_parse_note(name: str, midi: int) -> None:
    assert pitch.parse_note(name) == midi


@pytest.mark.parametrize("bad", ["", "4", "H4", "C", "Cb4"])
def test_parse_note_rejects_garbage(bad: str) -> None:
    with pytest.raises(ValueError, match=r"note|pitch class"):
        pitch.parse_note(bad)


def test_transpose_adds_a_constant() -> None:
    assert pitch.transpose([60, 64, 67], 4) == [64, 68, 71]


def test_pitch_class_wraps() -> None:
    assert pitch.pitch_class(60) == 0
    assert pitch.pitch_class(71) == 11
    assert pitch.pitch_class(72) == 0
