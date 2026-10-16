# Copyright (c) 2026 Krzysztof Rudnicki
"""Adding, removing, listing and the one-time legacy import."""

from __future__ import annotations

from datetime import date
import json
from typing import TYPE_CHECKING

import pytest

from sickdays._api import (
    actor_id,
    add_sick_day,
    import_legacy,
    is_sick_day,
    load,
    remove_sick_day,
    sick_days,
)
from sickdays._errors import (
    AlreadySickError,
    FreeDayConflictError,
    NotSickError,
    PastDateError,
)
from sickdays._paths import Paths

if TYPE_CHECKING:
    from pathlib import Path

TODAY = date(2026, 10, 16)
TOMORROW = date(2026, 10, 17)
YESTERDAY = date(2026, 10, 15)


def test_every_day_is_normal_by_default() -> None:
    assert not is_sick_day(TODAY)
    assert sick_days() == frozenset()


def test_adding_today_makes_it_a_sick_day() -> None:
    entry = add_sick_day(TODAY, now=TODAY)
    assert entry.is_sick
    assert is_sick_day(TODAY)
    assert is_sick_day(now=TODAY)


def test_there_is_no_cap() -> None:
    for offset in range(60):
        add_sick_day(date.fromordinal(TODAY.toordinal() + offset), now=TODAY)
    assert len(sick_days()) == 60


def test_a_past_day_cannot_be_added() -> None:
    with pytest.raises(PastDateError, match="already passed"):
        add_sick_day(YESTERDAY, now=TODAY)
    assert not is_sick_day(YESTERDAY)


def test_adding_twice_is_refused() -> None:
    add_sick_day(TOMORROW, now=TODAY)
    with pytest.raises(AlreadySickError):
        add_sick_day(TOMORROW, now=TODAY)


def test_a_free_day_cannot_become_a_sick_day() -> None:
    with pytest.raises(FreeDayConflictError, match="free day"):
        add_sick_day(TOMORROW, is_free=lambda _day: True, now=TODAY)
    assert not is_sick_day(TOMORROW)


def test_the_default_check_asks_the_free_day_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[date] = []

    def _free(day: date) -> bool:
        asked.append(day)
        return True

    monkeypatch.setattr("sickdays._api.free_day_predicate", lambda: _free)
    with pytest.raises(FreeDayConflictError):
        add_sick_day(TOMORROW, now=TODAY)
    assert asked == [TOMORROW]


def test_removing_makes_the_day_normal_again() -> None:
    add_sick_day(TOMORROW, now=TODAY)
    entry = remove_sick_day(TOMORROW, now=TODAY)
    assert not entry.is_sick
    assert not is_sick_day(TOMORROW)


def test_a_removed_day_can_be_added_again() -> None:
    add_sick_day(TODAY, now=TODAY)
    remove_sick_day(TODAY, now=TODAY)
    add_sick_day(TODAY, now=TODAY)
    assert is_sick_day(TODAY)


def test_a_past_day_cannot_be_removed() -> None:
    import_legacy([YESTERDAY])
    with pytest.raises(PastDateError, match="removed"):
        remove_sick_day(YESTERDAY, now=TODAY)
    assert is_sick_day(YESTERDAY)


def test_removing_a_normal_day_is_refused() -> None:
    with pytest.raises(NotSickError):
        remove_sick_day(TOMORROW, now=TODAY)


def test_the_legacy_import_writes_past_days() -> None:
    days = [date(2026, 7, 24), date(2026, 6, 21)]
    assert import_legacy(days) == sorted(days)
    assert sick_days() == frozenset(days)


def test_the_legacy_import_is_idempotent(state_dir: Path) -> None:
    import_legacy([date(2026, 6, 21)])
    assert import_legacy([date(2026, 6, 21), date(2026, 6, 21)]) == []
    lines = (state_dir / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["action"] for line in lines] == ["import"]


def test_every_change_is_audited(state_dir: Path) -> None:
    add_sick_day(TODAY, now=TODAY)
    remove_sick_day(TODAY, now=TODAY)
    lines = (state_dir / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["action"] for line in lines] == ["add", "remove"]


def test_the_actor_is_this_installs_uuid() -> None:
    entry = add_sick_day(TODAY, now=TODAY)
    assert entry.actor == actor_id()
    assert len(entry.actor) == 36


def test_an_explicit_pool_is_honoured(tmp_path: Path) -> None:
    paths = Paths.under(tmp_path / "elsewhere")
    add_sick_day(TOMORROW, paths=paths, now=TODAY)
    assert is_sick_day(TOMORROW, log_path=paths.log)
    assert sick_days(log_path=paths.log) == frozenset({TOMORROW})
    assert not is_sick_day(TOMORROW)
    assert load(paths.log)
