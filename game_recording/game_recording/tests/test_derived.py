# Copyright (c) 2026 Krzysztof Rudnicki
"""Derived moments: several telemetry entries that are one moment together."""

from game_recording import moments
from game_recording.tests.test_helpers import MOMENT_MAP, entry


def test_a_burst_of_hitches_is_one_moment() -> None:
    rows = [
        entry("hitch", 1000, 1, dur_ms=40, cause="load"),
        entry("hitch", 1500, 2, dur_ms=90),
        entry("hitch", 3400, 3, dur_ms=55),
    ]
    found = moments.derive(rows, MOMENT_MAP)
    assert len(found) == 1
    assert found[0]["kind"] == "hitch"
    assert (found[0]["count"], found[0]["max_ms"]) == (3, 90)
    assert found[0]["label"] == "hitch x3 max 90 ms"
    assert found[0]["ms"] == 1000, "stamped at the first hitch"
    assert found[0]["cause"] == "load"
    assert found[0]["derived"]


def test_hitches_far_apart_are_separate_moments() -> None:
    gap_ms = int(MOMENT_MAP.hitch_merge_s * 1000) + 1
    rows = [entry("hitch", 1000, 1, dur_ms=40), entry("hitch", 1000 + gap_ms, 2, dur_ms=20)]
    found = moments.derive(rows, MOMENT_MAP)
    assert [m["label"] for m in found] == ["hitch x1 max 40 ms", "hitch x1 max 20 ms"]


def test_a_hitch_without_a_duration_counts_as_zero() -> None:
    assert moments.derive([entry("hitch", 1000, 1)], MOMENT_MAP)[0]["max_ms"] == 0


def test_other_entries_derive_nothing() -> None:
    rows = [entry("game_start", 1000, 1, game="watch"), entry("command", 2000, 2, order="charge")]
    assert moments.derive(rows, MOMENT_MAP) == []
    assert moments.derive([], MOMENT_MAP) == []
