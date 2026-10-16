# Copyright (c) 2026 Krzysztof Rudnicki
"""stands_down, kept_lockers, add --keep and the keep edit, end to end."""

from __future__ import annotations

from datetime import date
import json
from typing import TYPE_CHECKING

from crdt_sync import Hlc, Record, merge_logs
import pytest

from sickdays._api import add_sick_day, is_sick_day, load, remove_sick_day
from sickdays._constants import LOCKERS
from sickdays._errors import NotSickError, PastDateError
from sickdays._keep_api import kept_lockers, set_kept_lockers, stands_down
from sickdays._store import write_pool

if TYPE_CHECKING:
    from pathlib import Path

TODAY = date(2026, 10, 16)
TOMORROW = date(2026, 10, 17)
KEY = "2026-10-17"

#: A record exactly as 0.1.0 wrote the live 2026-10-16..20 days: no keep.
V010_RECORD = {
    "id": KEY,
    "fields": {
        "state": ["sick", "2026-10-16T08:12:03.517Z-0000-phone"],
        "actor": ["phone", "2026-10-16T08:12:03.517Z-0000-phone"],
    },
    "deleted": False,
    "deleted_hlc": None,
}


def _pool(state_dir: Path) -> Path:
    return state_dir / "sick_days.json"


def _raw(state_dir: Path, record: dict[str, object]) -> None:
    _pool(state_dir).write_text(json.dumps({KEY: record}), encoding="utf-8")


def test_a_normal_day_stands_nothing_down() -> None:
    assert not any(stands_down(locker, TOMORROW) for locker in LOCKERS)
    assert kept_lockers(TOMORROW) == frozenset()


def test_a_sick_day_with_no_keep_stands_everything_down() -> None:
    add_sick_day(TOMORROW, now=TODAY)
    assert all(stands_down(locker, TOMORROW) for locker in LOCKERS)
    assert kept_lockers(TOMORROW) == frozenset()


def test_a_kept_locker_applies_and_the_rest_stand_down() -> None:
    entry = add_sick_day(TOMORROW, keep=["leetcode", "leetcode"], now=TODAY)
    assert entry.keep == {"leetcode"}
    assert not stands_down("leetcode", TOMORROW)
    assert stands_down("workout", TOMORROW)
    assert kept_lockers(TOMORROW) == {"leetcode"}
    assert is_sick_day(TOMORROW)


def test_today_is_the_default_day() -> None:
    add_sick_day(TODAY, keep=["diet"], now=TODAY)
    assert stands_down("book", now=TODAY)
    assert not stands_down("diet", now=TODAY)
    assert kept_lockers(now=TODAY) == {"diet"}


def test_the_add_writes_a_sorted_keep_on_one_tick(state_dir: Path) -> None:
    add_sick_day(TOMORROW, keep=["workout", "alarm"], now=TODAY)
    fields = json.loads(_pool(state_dir).read_text(encoding="utf-8"))[KEY]["fields"]
    assert fields["keep"][0] == ["alarm", "workout"]
    assert fields["keep"][1] == fields["state"][1] == fields["actor"][1]


def test_an_unknown_locker_on_add_writes_nothing(state_dir: Path) -> None:
    with pytest.raises(ValueError, match="unknown locker"):
        add_sick_day(TOMORROW, keep=["leetcod"], now=TODAY)
    assert not _pool(state_dir).exists()


def test_an_unknown_locker_question_is_a_programmer_error() -> None:
    with pytest.raises(ValueError, match="unknown locker"):
        stands_down("leetcod", TOMORROW)


def test_a_0_1_0_record_stands_every_locker_down(state_dir: Path) -> None:
    _raw(state_dir, V010_RECORD)
    assert all(stands_down(locker, TOMORROW) for locker in LOCKERS)
    assert kept_lockers(TOMORROW) == frozenset()


def test_a_malformed_keep_means_the_locks_apply(state_dir: Path) -> None:
    record = json.loads(json.dumps(V010_RECORD))
    record["fields"]["keep"] = ["leetcode", "2026-10-16T08:12:03.517Z-0000-phone"]
    _raw(state_dir, record)
    assert not any(stands_down(locker, TOMORROW) for locker in LOCKERS)
    assert kept_lockers(TOMORROW) == frozenset(LOCKERS)


def test_an_unreadable_pool_stands_nothing_down(state_dir: Path) -> None:
    _pool(state_dir).write_text("{not json", encoding="utf-8")
    assert not stands_down("alarm", TOMORROW)
    assert kept_lockers(TOMORROW) == frozenset()


def test_set_kept_lockers_replaces_the_set(state_dir: Path) -> None:
    add_sick_day(TOMORROW, keep=["book"], now=TODAY)
    entry = set_kept_lockers(TOMORROW, ["alarm", "diet"], now=TODAY)
    assert entry.keep == {"alarm", "diet"}
    assert kept_lockers(TOMORROW) == {"alarm", "diet"}
    assert stands_down("book", TOMORROW)
    set_kept_lockers(TOMORROW, [], now=TODAY)
    assert all(stands_down(locker, TOMORROW) for locker in LOCKERS)
    lines = (state_dir / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    events = [json.loads(line) for line in lines]
    assert [(e["action"], e["keep"]) for e in events] == [
        ("add", ["book"]),
        ("keep", ["alarm", "diet"]),
        ("keep", []),
    ]


def test_a_keep_edit_does_not_restamp_state(state_dir: Path) -> None:
    add_sick_day(TOMORROW, now=TODAY)
    before = load()[KEY].fields["state"]
    set_kept_lockers(TOMORROW, ["leetcode"], now=TODAY)
    after = load()[KEY]
    assert after.fields["state"] == before
    assert after.fields["keep"][1] > before[1]
    assert after.fields["actor"][1] == after.fields["keep"][1]


def test_a_keep_edit_never_reasserts_sick_over_a_concurrent_clear() -> None:
    add_sick_day(TOMORROW, now=TODAY)
    added = load()
    set_kept_lockers(TOMORROW, ["leetcode"], now=TODAY)
    edited = load()
    state_tick = added[KEY].fields["state"][1]
    # "!" sorts before any uuid, so this clear is concurrent with, and
    # older than, the keep edit -- the case a re-stamped state would win.
    clear_tick = Hlc(state_tick.wall_time_ms, state_tick.counter + 1, "!")
    assert edited[KEY].fields["keep"][1] > clear_tick
    cleared = Record(
        id=KEY,
        fields={
            "state": ("cleared", clear_tick),
            "actor": ("phone", clear_tick),
            "keep": ([], clear_tick),
        },
    )
    merged = merge_logs(edited, {KEY: cleared})
    assert merged[KEY].fields["state"][0] == "cleared"


def test_a_keep_edit_beats_a_state_from_a_clock_that_runs_ahead(
    state_dir: Path,
) -> None:
    future = "2099-01-01T00:00:00.000Z-0000-phone"
    record = json.loads(json.dumps(V010_RECORD))
    record["fields"]["state"][1] = future
    record["fields"]["actor"][1] = future
    _raw(state_dir, record)
    set_kept_lockers(TOMORROW, ["workout"], now=TODAY)
    assert kept_lockers(TOMORROW) == {"workout"}
    assert not stands_down("workout", TOMORROW)


def test_a_clear_and_re_add_drops_a_stale_keep_from_another_node() -> None:
    add_sick_day(TOMORROW, keep=["leetcode"], now=TODAY)
    old_copy = load()
    remove_sick_day(TOMORROW, now=TODAY)
    add_sick_day(TOMORROW, now=TODAY)
    merged = merge_logs(load(), old_copy)
    assert merged[KEY].fields["keep"][0] == []


def test_a_0_1_0_re_add_makes_an_older_keep_stale(state_dir: Path) -> None:
    add_sick_day(TOMORROW, keep=["leetcode"], now=TODAY)
    newer = "2099-01-01T00:00:00.000Z-0000-oldphone"
    record = json.loads(json.dumps(V010_RECORD))
    record["fields"]["state"] = ["sick", newer]
    merged = merge_logs(load(), {KEY: Record.from_dict(record)})
    write_pool(_pool(state_dir), merged)
    assert stands_down("leetcode", TOMORROW)


def test_the_keep_edit_refusals() -> None:
    with pytest.raises(NotSickError):
        set_kept_lockers(TOMORROW, ["book"], now=TODAY)
    with pytest.raises(PastDateError, match="changed"):
        set_kept_lockers(date(2026, 10, 15), ["book"], now=TODAY)
    add_sick_day(TOMORROW, now=TODAY)
    with pytest.raises(ValueError, match="unknown locker"):
        set_kept_lockers(TOMORROW, ["nope"], now=TODAY)
    remove_sick_day(TOMORROW, now=TODAY)
    with pytest.raises(NotSickError):
        set_kept_lockers(TOMORROW, ["book"], now=TODAY)
