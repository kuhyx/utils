"""Marking, releasing, and the budget arithmetic behind both."""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

import pytest

from freedays._api import (
    actor_id,
    is_free_day,
    load,
    lookup,
    mark,
    release,
    save,
    status,
)
from freedays._errors import (
    AlreadyFreeError,
    BudgetExhaustedError,
    NotFreeError,
    PastDateError,
)

if TYPE_CHECKING:
    from pathlib import Path

TODAY = date(2026, 9, 7)
TOMORROW = date(2026, 9, 8)
YESTERDAY = date(2026, 9, 6)


def test_an_untouched_day_is_not_free() -> None:
    assert not is_free_day(TODAY, now=TODAY)


def test_marking_a_day_makes_it_free() -> None:
    mark(TODAY, now=TODAY)
    assert is_free_day(TODAY, now=TODAY)


def test_is_free_day_defaults_to_today() -> None:
    mark(TODAY, now=TODAY)
    assert is_free_day(now=TODAY)


def test_marking_one_day_does_not_free_its_neighbour() -> None:
    mark(TODAY, now=TODAY)
    assert not is_free_day(TOMORROW, now=TODAY)


def test_an_unreadable_pool_means_the_normal_rules_apply(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{ this is not json", encoding="utf-8")
    assert not is_free_day(TODAY, log_path=corrupt, now=TODAY)


def test_a_reason_is_stored_but_never_required() -> None:
    mark(TODAY, reason="wedding", now=TODAY)
    entry = lookup(TODAY, now=TODAY)
    assert entry is not None
    assert entry.reason == "wedding"


def test_marking_without_a_reason_is_fine() -> None:
    entry = mark(TOMORROW, now=TODAY)
    assert entry.reason == ""


def test_lookup_defaults_to_today_and_returns_none_for_an_untouched_day() -> None:
    assert lookup(now=TODAY) is None


def test_a_past_day_cannot_be_marked() -> None:
    with pytest.raises(PastDateError, match="already passed"):
        mark(YESTERDAY, now=TODAY)


def test_marking_an_already_free_day_is_refused() -> None:
    mark(TOMORROW, now=TODAY)
    with pytest.raises(AlreadyFreeError, match="already a free day"):
        mark(TOMORROW, now=TODAY)


def test_the_annual_budget_is_enforced() -> None:
    for offset in range(3):
        mark(date(2026, 10, 1 + offset), now=TODAY, budget=3)
    with pytest.raises(BudgetExhaustedError, match="no free days left in 2026"):
        mark(date(2026, 11, 1), now=TODAY, budget=3)


def test_the_budget_is_per_calendar_year_of_the_day_being_marked() -> None:
    for offset in range(3):
        mark(date(2026, 10, 1 + offset), now=TODAY, budget=3)
    # 2027 has its own allowance; Jan 1 resets it.
    assert mark(date(2027, 1, 2), now=TODAY, budget=3).is_free


def test_consecutive_days_are_allowed() -> None:
    """A fortnight in a row -- the whole reason these are not sick days."""
    for offset in range(14):
        mark(date(2026, 10, 1) + timedelta(days=offset), now=TODAY)
    assert is_free_day(date(2026, 10, 14), now=TODAY)


def test_releasing_a_day_that_was_never_free_is_refused() -> None:
    with pytest.raises(NotFreeError, match="not a free day"):
        release(TOMORROW, now=TODAY)


def test_releasing_an_already_released_day_is_refused() -> None:
    mark(TOMORROW, now=TODAY)
    release(TOMORROW, now=TODAY)
    with pytest.raises(NotFreeError):
        release(TOMORROW, now=TODAY)


def test_releasing_a_future_day_refunds_it() -> None:
    mark(TOMORROW, now=TODAY)
    assert status(now=TODAY).left == 34
    entry = release(TOMORROW, now=TODAY)
    assert not entry.consumed
    assert status(now=TODAY).left == 35


def test_releasing_today_does_not_refund_it() -> None:
    mark(TODAY, now=TODAY)
    entry = release(TODAY, now=TODAY)
    assert entry.consumed
    assert not is_free_day(TODAY, now=TODAY)
    assert status(now=TODAY).left == 34


def test_a_day_released_after_it_arrived_stays_spent() -> None:
    mark(TOMORROW, now=TODAY)
    # The day arrives, then is released the day after.
    entry = release(TOMORROW, now=date(2026, 9, 9))
    assert entry.consumed
    assert status(now=TODAY).left == 34


def test_a_day_marked_today_is_immediately_consumed() -> None:
    assert mark(TODAY, now=TODAY).consumed


def test_a_day_marked_ahead_is_not_yet_consumed() -> None:
    assert not mark(TOMORROW, now=TODAY).consumed


def test_a_released_future_day_can_be_marked_again() -> None:
    mark(TOMORROW, now=TODAY)
    release(TOMORROW, now=TODAY)
    assert mark(TOMORROW, now=TODAY).is_free


def test_re_marking_a_consumed_day_keeps_it_consumed() -> None:
    mark(TODAY, now=TODAY)
    release(TODAY, now=TODAY)
    assert mark(TODAY, now=TODAY).consumed


def test_status_reports_the_year_the_budget_and_what_is_booked() -> None:
    mark(TODAY, now=TODAY)
    mark(date(2026, 12, 24), now=TODAY)
    current = status(now=TODAY)
    assert current.year == 2026
    assert current.budget == 35
    assert current.spent == 2
    assert current.left == 33
    assert current.today_is_free
    assert current.upcoming == [date(2026, 12, 24)]
    assert current.taken == [TODAY, date(2026, 12, 24)]


def test_status_can_be_asked_about_another_year() -> None:
    mark(date(2027, 3, 1), now=TODAY)
    assert status(year=2027, now=TODAY).spent == 1
    assert status(year=2026, now=TODAY).spent == 0


def test_status_left_never_goes_negative() -> None:
    mark(TOMORROW, now=TODAY)
    mark(date(2026, 9, 9), now=TODAY)
    assert status(now=TODAY, budget=1).left == 0


def test_the_device_id_is_a_persisted_uuid_not_a_fixed_constant() -> None:
    first = actor_id()
    assert first not in {"pc", "phone", ""}
    assert actor_id() == first


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    mark(TOMORROW, now=TODAY)
    elsewhere = tmp_path / "copy.json"
    save(load(), elsewhere)
    assert is_free_day(TOMORROW, log_path=elsewhere, now=TODAY)
