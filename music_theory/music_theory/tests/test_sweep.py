# Copyright (c) 2026 Krzysztof Rudnicki
import numpy as np
import pytest

from music_theory import analysis, sweep

RATE = 44100


def _rng(seed: int = 5) -> np.random.Generator:
    return np.random.default_rng(seed)


def _curve(pitch: sweep.Pitch, frames: int = RATE, seed: int = 5) -> np.ndarray:
    return sweep.frequency_curve(pitch, frames, _rng(seed), RATE)


def test_glide_is_exponential_between_breakpoints() -> None:
    times = np.array([0.0, 0.5, 1.0, 2.0])
    curve = sweep.glide((100.0, 400.0), times, 1.0)
    assert curve.tolist() == pytest.approx([100.0, 200.0, 400.0, 400.0])


def test_glide_with_three_points_goes_up_then_down() -> None:
    times = np.array([0.0, 0.5, 1.0])
    assert sweep.glide((300.0, 1500.0, 400.0), times, 1.0).tolist() == pytest.approx(
        [300.0, 1500.0, 400.0]
    )


def test_glide_single_point_and_zero_span_are_constant() -> None:
    times = np.array([0.0, 0.3])
    assert sweep.glide((220.0,), times, 1.0).tolist() == [220.0, 220.0]
    assert sweep.glide((220.0, 880.0), times, 0.0).tolist() == [880.0, 880.0]


def test_glide_rejects_empty_and_non_positive_points() -> None:
    with pytest.raises(ValueError, match="positive"):
        sweep.glide((), np.zeros(2), 1.0)
    with pytest.raises(ValueError, match="positive"):
        sweep.glide((100.0, 0.0), np.zeros(2), 1.0)


def test_sweep_up_moves_the_fft_peak_up() -> None:
    freq = _curve(sweep.Pitch(hz=(300.0, 2400.0)))
    signal = sweep.phase_oscillator(freq, "sine", RATE)
    quarter = RATE // 4
    early = analysis.dominant_frequency(signal[:quarter], RATE)
    late = analysis.dominant_frequency(signal[-quarter:], RATE)
    assert early < 700.0
    assert late > 1200.0


def test_phase_oscillator_has_no_jumps_on_a_sweep() -> None:
    freq = _curve(sweep.Pitch(hz=(100.0, 4000.0)))
    signal = sweep.phase_oscillator(freq, "sine", RATE)
    step = 2.0 * np.pi * 4000.0 / RATE
    assert float(np.max(np.abs(np.diff(signal)))) <= step * 1.01
    assert signal[0] == 0.0


def test_phase_oscillator_constant_pitch_and_duty() -> None:
    freq = np.full(RATE // 2, 440.0)
    tone = sweep.phase_oscillator(freq, "square", RATE)
    assert analysis.dominant_frequency(tone, RATE) == pytest.approx(440.0, abs=2.0)
    narrow = sweep.phase_oscillator(freq, "square", RATE, duty=0.125)
    assert float(np.mean(narrow)) == pytest.approx(-0.75, abs=0.02)
    assert sweep.phase_oscillator(np.zeros(0), "sine", RATE).size == 0


def test_glide_seconds_limits_the_slide() -> None:
    freq = _curve(sweep.Pitch(hz=(200.0, 800.0), glide=0.1))
    assert freq[int(0.05 * RATE)] == pytest.approx(400.0, rel=1e-3)
    assert freq[int(0.5 * RATE)] == pytest.approx(800.0)


def test_retrigger_restarts_the_slide() -> None:
    pitch = sweep.Pitch(hz=(300.0, 1200.0), glide=0.03, repeat=0.05)
    freq = _curve(pitch)
    period = int(0.05 * RATE)
    assert freq[0] == pytest.approx(300.0)
    assert freq[period + 1] < freq[period - 1]
    assert freq[2 * period + 10] == pytest.approx(freq[10], rel=1e-2)


def test_arpeggio_steps_the_pitch() -> None:
    freq = _curve(sweep.Pitch(hz=(400.0,), arp_ratio=1.5, arp_at=0.1))
    assert freq[int(0.05 * RATE)] == pytest.approx(400.0)
    assert freq[int(0.2 * RATE)] == pytest.approx(600.0)


def test_arpeggio_restarts_with_the_retrigger() -> None:
    pitch = sweep.Pitch(hz=(400.0,), arp_ratio=2.0, arp_at=0.02, repeat=0.04)
    freq = _curve(pitch)
    assert freq[int(0.03 * RATE)] == pytest.approx(800.0)
    assert freq[int(0.045 * RATE)] == pytest.approx(400.0)


def test_vibrato_wobbles_within_its_depth() -> None:
    freq = _curve(sweep.Pitch(hz=(440.0,), vibrato_semitones=1.0, vibrato_hz=6.0))
    assert float(np.max(freq)) == pytest.approx(440.0 * 2 ** (1 / 12), rel=1e-3)
    assert float(np.min(freq)) == pytest.approx(440.0 * 2 ** (-1 / 12), rel=1e-3)


def test_random_jumps_hold_then_step_and_are_seeded() -> None:
    pitch = sweep.Pitch(hz=(500.0,), jump_semitones=6.0, jump_every=0.01)
    freq = _curve(pitch)
    hold = int(0.01 * RATE)
    assert np.all(freq[:hold] == freq[0])
    assert len(np.unique(freq)) > 50
    ratio = freq / 500.0
    assert float(np.max(ratio)) <= 2 ** (6 / 12) + 1e-9
    assert float(np.min(ratio)) >= 2 ** (-6 / 12) - 1e-9
    assert np.array_equal(freq, _curve(pitch))
    assert not np.array_equal(freq, _curve(pitch, seed=6))


def test_frequency_curve_of_no_frames() -> None:
    assert _curve(sweep.Pitch(), frames=0).size == 0


def test_ring_modulation_moves_energy_to_sum_and_difference() -> None:
    carrier = sweep.phase_oscillator(np.full(RATE, 1000.0), "sine", RATE)
    ringed = sweep.ring_modulate(carrier, 300.0, RATE)

    def near(hz: float) -> float:
        return analysis.band_energy(ringed, hz - 20.0, hz + 20.0, RATE)

    assert near(700.0) > 100 * near(1000.0)
    assert near(1300.0) > 100 * near(1000.0)
    assert np.array_equal(sweep.ring_modulate(carrier, 0.0, RATE), carrier)
