# Copyright (c) 2026 Krzysztof Rudnicki
from typing import cast

import numpy as np
import pytest

from music_theory import analysis, synth


def test_time_axis_length_and_negative() -> None:
    assert len(synth.time_axis(1.0, 100)) == 100
    assert len(synth.time_axis(-1.0, 100)) == 0


@pytest.mark.parametrize("waveform", synth.WAVEFORMS)
def test_every_waveform_peaks_at_its_frequency(waveform: synth.Waveform) -> None:
    signal = synth.oscillator(440.0, 1.0, waveform)
    assert analysis.dominant_frequency(signal) == pytest.approx(440.0, abs=1.0)
    assert np.max(np.abs(signal)) <= 1.0


def test_oscillator_rejects_unknown_waveform() -> None:
    with pytest.raises(ValueError, match="unknown waveform"):
        synth.oscillator(440.0, 0.1, cast("synth.Waveform", "noise"))


def test_square_is_two_valued() -> None:
    assert set(np.unique(synth.oscillator(10.0, 0.5, "square"))) == {-1.0, 1.0}


def test_additive_stacks_harmonics() -> None:
    signal = synth.additive(100.0, 1.0, [0.0, 1.0])
    assert analysis.dominant_frequency(signal) == pytest.approx(200.0, abs=1.0)


def test_adsr_shape() -> None:
    gain = synth.adsr(synth.Envelope(0.1, 0.1, 0.5, 0.1), 1.0, 100)
    assert len(gain) == 100
    assert gain[0] == 0.0
    assert gain[10] == pytest.approx(1.0)
    assert gain[50] == pytest.approx(0.5)
    assert gain[-1] < 0.5
    assert gain[-1] >= 0.0


def test_adsr_longer_than_the_note_is_clamped() -> None:
    gain = synth.adsr(synth.Envelope(1.0, 1.0, 0.5, 1.0), 0.1, 100)
    assert len(gain) == 10
    assert np.all(gain >= 0.0)
    assert synth.adsr(synth.Envelope(), -1.0, 100).size == 0


def test_lowpass_darkens_and_zero_cutoff_silences() -> None:
    saw = synth.oscillator(220.0, 0.5, "saw")
    dark = synth.lowpass(saw, 500.0)
    assert analysis.spectral_centroid(dark) < analysis.spectral_centroid(saw)
    assert not np.any(synth.lowpass(saw, 0.0))


def test_detune_by_cents() -> None:
    assert synth.detune(440.0, 1200.0) == pytest.approx(880.0)
    assert synth.detune(440.0, 0.0) == 440.0


def test_mix_pads_shorter_signals() -> None:
    mixed = synth.mix(np.ones(3), np.ones(5))
    assert list(mixed) == [2.0, 2.0, 2.0, 1.0, 1.0]
    assert synth.mix().size == 0


def test_normalize_scales_peak_and_keeps_silence() -> None:
    assert np.max(np.abs(synth.normalize(np.array([0.1, -0.2])))) == pytest.approx(0.8)
    assert not np.any(synth.normalize(np.zeros(4)))
    assert synth.normalize(np.zeros(0)).size == 0


def test_to_int16_clips() -> None:
    out = synth.to_int16(np.array([2.0, -2.0, 0.0]))
    assert list(out) == [32767, -32767, 0]
    assert out.dtype == np.int16
