# Copyright (c) 2026 Krzysztof Rudnicki
"""Records, and how two devices' copies of a date converge."""

from __future__ import annotations

from datetime import date

from crdt_sync import Hlc, Record, merge_logs

from sickdays._model import (
    SickDay,
    build_record,
    is_sick_record,
    latest_hlc,
    sick_dates,
    to_sick_day,
)

DAY = date(2026, 10, 20)


def _tick(node: str, wall_ms: int) -> Hlc:
    return Hlc(wall_time_ms=wall_ms, counter=0, node_id=node)


def _record(*, sick: bool, node: str, wall_ms: int) -> Record:
    return build_record(SickDay(DAY, is_sick=sick, actor=node), _tick(node, wall_ms))


def test_a_record_round_trips() -> None:
    record = _record(sick=True, node="pc", wall_ms=1)
    assert to_sick_day(record) == SickDay(DAY, is_sick=True, actor="pc")


def test_a_later_removal_on_another_device_wins_everywhere() -> None:
    added = {"2026-10-20": _record(sick=True, node="pc", wall_ms=1)}
    removed = {"2026-10-20": _record(sick=False, node="phone", wall_ms=2)}
    assert sick_dates(merge_logs(added, removed)) == frozenset()
    assert sick_dates(merge_logs(removed, added)) == frozenset()


def test_a_later_re_add_wins_over_an_earlier_removal() -> None:
    removed = {"2026-10-20": _record(sick=False, node="pc", wall_ms=2)}
    added_again = {"2026-10-20": _record(sick=True, node="phone", wall_ms=3)}
    assert sick_dates(merge_logs(removed, added_again)) == {DAY}
    assert sick_dates(merge_logs(added_again, removed)) == {DAY}


def test_a_tombstone_never_reads_as_sick() -> None:
    record = _record(sick=True, node="pc", wall_ms=1)
    tombstoned = Record(id=record.id, fields=record.fields, deleted=True)
    assert not is_sick_record(tombstoned)


def test_junk_ids_and_odd_values_are_tolerated() -> None:
    junk = Record(id="not-a-date", fields={"state": ("sick", _tick("pc", 1))})
    assert to_sick_day(junk) is None
    odd = Record(id="2026-10-20", fields={"state": (7, _tick("pc", 1))})
    assert not is_sick_record(odd)
    assert to_sick_day(odd) == SickDay(DAY, is_sick=False, actor="")
    assert sick_dates({"x": junk, "y": odd}) == frozenset()


def test_latest_hlc_is_per_node() -> None:
    log = {
        "a": _record(sick=True, node="pc", wall_ms=5),
        "b": _record(sick=True, node="phone", wall_ms=9),
    }
    assert latest_hlc(log, "pc") == _tick("pc", 5)
    assert latest_hlc(log, "tablet") is None
