"""Tests for the Hybrid Logical Clock."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from crdt_sync import Hlc

if TYPE_CHECKING:
    from collections.abc import Callable


class TestOrdering:
    def test_greater_wall_time_wins(self, make_hlc: Callable[..., Hlc]) -> None:
        assert make_hlc(200) > make_hlc(100)

    def test_equal_wall_time_greater_counter_wins(
        self, make_hlc: Callable[..., Hlc]
    ) -> None:
        assert make_hlc(100, counter=2) > make_hlc(100, counter=1)

    def test_equal_wall_time_and_counter_breaks_tie_on_node_id(
        self, make_hlc: Callable[..., Hlc]
    ) -> None:
        assert make_hlc(100, counter=1, node_id="b") > make_hlc(
            100, counter=1, node_id="a"
        )

    def test_identical_clocks_compare_equal(self, make_hlc: Callable[..., Hlc]) -> None:
        assert make_hlc(100, counter=1, node_id="a") == make_hlc(
            100, counter=1, node_id="a"
        )


class TestNewTick:
    def test_first_tick_has_counter_zero(self) -> None:
        tick = Hlc.new_tick("node-a", wall_time_ms=1000)
        assert tick == Hlc(wall_time_ms=1000, counter=0, node_id="node-a")

    def test_advancing_wall_clock_resets_counter(
        self, make_hlc: Callable[..., Hlc]
    ) -> None:
        previous = make_hlc(1000, counter=5)
        tick = Hlc.new_tick("node-a", previous=previous, wall_time_ms=2000)
        assert tick == Hlc(wall_time_ms=2000, counter=0, node_id="node-a")

    def test_stalled_wall_clock_increments_counter(
        self, make_hlc: Callable[..., Hlc]
    ) -> None:
        previous = make_hlc(1000, counter=5)
        tick = Hlc.new_tick("node-a", previous=previous, wall_time_ms=1000)
        assert tick == Hlc(wall_time_ms=1000, counter=6, node_id="node-a")

    def test_regressed_wall_clock_still_advances_monotonically(
        self, make_hlc: Callable[..., Hlc]
    ) -> None:
        previous = make_hlc(1000, counter=5)
        tick = Hlc.new_tick("node-a", previous=previous, wall_time_ms=500)
        assert tick == Hlc(wall_time_ms=1000, counter=6, node_id="node-a")

    def test_defaults_to_the_real_clock_when_unset(self) -> None:
        tick = Hlc.new_tick("node-a")
        assert tick.node_id == "node-a"
        assert tick.wall_time_ms > 0


class TestStringRoundTrip:
    def test_round_trips_through_to_str_and_from_str(
        self, make_hlc: Callable[..., Hlc]
    ) -> None:
        original = make_hlc(1_751_000_123_456, counter=7, node_id="phone")
        assert Hlc.from_str(original.to_str()) == original

    def test_to_str_is_lexicographically_sortable_by_wall_time(
        self, make_hlc: Callable[..., Hlc]
    ) -> None:
        earlier = make_hlc(1000)
        later = make_hlc(2000)
        assert earlier.to_str() < later.to_str()

    def test_to_str_is_lexicographically_sortable_by_counter(
        self, make_hlc: Callable[..., Hlc]
    ) -> None:
        lower = make_hlc(1000, counter=1)
        higher = make_hlc(1000, counter=200)
        assert lower.to_str() < higher.to_str()

    def test_from_str_rejects_a_missing_z_separator(self) -> None:
        with pytest.raises(ValueError, match="not a valid Hlc string"):
            Hlc.from_str("not-a-valid-clock-string-at-all")

    def test_from_str_rejects_a_wrong_length_iso_prefix(self) -> None:
        with pytest.raises(ValueError, match="not a valid Hlc string"):
            Hlc.from_str("2026-07-05T12:00:00Z-0000-node-a")

    def test_from_str_rejects_a_missing_node_id_separator(self) -> None:
        with pytest.raises(ValueError, match="not a valid Hlc string"):
            Hlc.from_str("2026-07-05T12:00:00.000Z-0000")
