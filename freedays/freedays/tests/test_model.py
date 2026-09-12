# Copyright (c) 2026 Krzysztof Rudnicki
"""Record translation, and the CRDT properties the design leans on."""

from __future__ import annotations

from datetime import date

from crdt_sync import Hlc, Record, merge_logs, merge_record

from freedays._constants import FIELD_CONSUMED, FIELD_STATE, STATE_FREE
from freedays._model import (
    FreeDay,
    build_record,
    is_consumed_record,
    is_free_record,
    latest_hlc,
    to_free_day,
)

DAY = date(2026, 12, 24)


def _record(
    *, free: bool, consumed: bool = False, node: str = "a", ms: int = 1000
) -> Record:
    return build_record(
        FreeDay(day=DAY, is_free=free, consumed=consumed, actor=node),
        Hlc(wall_time_ms=ms, counter=0, node_id=node),
    )


def test_the_record_id_is_the_date_so_two_devices_converge() -> None:
    assert _record(free=True).id == "2026-12-24"


def test_a_marked_record_reads_as_free() -> None:
    assert is_free_record(_record(free=True))


def test_a_cleared_record_does_not_read_as_free() -> None:
    assert not is_free_record(_record(free=False))


def test_a_tombstoned_record_is_never_free() -> None:
    tombstoned = Record(
        id="2026-12-24",
        fields={FIELD_STATE: (STATE_FREE, Hlc(1, 0, "a"))},
        deleted=True,
    )
    assert not is_free_record(tombstoned)


def test_consumed_defaults_to_false_when_the_field_is_absent() -> None:
    bare = Record(id="2026-12-24", fields={})
    assert not is_consumed_record(bare)


def test_to_free_day_reports_state_and_consumption() -> None:
    entry = to_free_day(_record(free=True, consumed=True))
    assert entry is not None
    assert entry.day == DAY
    assert entry.is_free
    assert entry.consumed


def test_to_free_day_rejects_a_record_whose_id_is_not_a_date() -> None:
    assert to_free_day(Record(id="not-a-date", fields={})) is None


def test_a_non_string_field_value_reads_as_empty() -> None:
    weird = Record(id="2026-12-24", fields={FIELD_STATE: (17, Hlc(1, 0, "a"))})
    entry = to_free_day(weird)
    assert entry is not None
    assert not entry.is_free


def test_latest_hlc_is_none_for_a_node_that_has_written_nothing() -> None:
    assert latest_hlc({"2026-12-24": _record(free=True, node="a")}, "b") is None


def test_latest_hlc_finds_this_nodes_greatest_tick() -> None:
    log = {
        "2026-12-24": _record(free=True, node="a", ms=5000),
        "2026-12-25": build_record(
            FreeDay(day=date(2026, 12, 25), is_free=True, actor="a"),
            Hlc(wall_time_ms=9000, counter=0, node_id="a"),
        ),
    }
    found = latest_hlc(log, "a")
    assert found is not None
    assert found.wall_time_ms == 9000


def test_marking_then_clearing_the_same_day_converges_to_the_later_write() -> None:
    marked = _record(free=True, node="a", ms=1000)
    cleared = _record(free=False, node="b", ms=2000)
    assert not is_free_record(merge_record(marked, cleared))
    assert not is_free_record(merge_record(cleared, marked))


def test_a_cleared_day_can_be_marked_free_again() -> None:
    """The reason un-marking flips a field instead of tombstoning."""
    cleared = _record(free=False, node="a", ms=1000)
    remarked = _record(free=True, node="b", ms=2000)
    assert is_free_record(merge_record(cleared, remarked))


def test_merge_is_commutative_and_idempotent_over_a_log() -> None:
    left = {"2026-12-24": _record(free=True, node="a", ms=1000)}
    right = {"2026-12-25": _record(free=False, node="b", ms=2000)}
    assert merge_logs(left, right) == merge_logs(right, left)
    assert merge_logs(left, left) == left


def test_consumed_survives_a_merge_with_a_later_unconsumed_write() -> None:
    """Sticky consumption is what stops a spent day being handed back."""
    spent = _record(free=True, consumed=True, node="a", ms=1000)
    later = _record(free=False, consumed=True, node="b", ms=2000)
    merged = merge_record(spent, later)
    assert merged.fields[FIELD_CONSUMED][0] is True
