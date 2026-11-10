# Copyright (c) 2026 Krzysztof Rudnicki
"""add_trip / answer_weekend only ever get stricter."""

from __future__ import annotations

from datetime import date

import pytest

import focus_project as fp
from focus_project import evidence
from focus_project.tests.helpers import SAT1, at, make, states


def _ms(day: int, hour: int) -> int:
    return int(at(day, hour).timestamp() * 1000)


def test_add_trip_records_when_it_was_entered() -> None:
    make()
    p = fp.add_trip("iv", date(2026, 11, 20), date(2026, 11, 22), now=at(10, 9))
    assert p.trips == (fp.Trip(date(2026, 11, 20), date(2026, 11, 22), _ms(10, 9)),)
    assert fp.list_projects() == [p]


def test_extending_keeps_entry_time_moving_earlier_resets_it() -> None:
    make()
    fp.add_trip("iv", date(2026, 11, 20), date(2026, 11, 21), now=at(10, 9))
    later = fp.add_trip("iv", date(2026, 11, 20), date(2026, 11, 23), now=at(11, 9))
    assert later.trips == (fp.Trip(date(2026, 11, 20), date(2026, 11, 23), _ms(10, 9)),)
    earlier = fp.add_trip("iv", date(2026, 11, 19), date(2026, 11, 23), now=at(12, 9))
    assert earlier.trips == (
        fp.Trip(date(2026, 11, 19), date(2026, 11, 23), _ms(12, 9)),
    )


def test_second_disjoint_trip_and_idempotent_repeat() -> None:
    make()
    fp.add_trip("iv", date(2026, 11, 13), date(2026, 11, 14), now=at(10, 9))
    fp.add_trip("iv", date(2026, 11, 20), date(2026, 11, 21), now=at(10, 10))
    again = fp.add_trip("iv", date(2026, 11, 20), date(2026, 11, 21), now=at(11, 9))
    assert len(again.trips) == 2
    assert again.trips[1].entered_ms == _ms(10, 10)


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (date(2026, 11, 21), date(2026, 11, 22)),  # starts later: loosens
        (date(2026, 11, 20), date(2026, 11, 21)),  # ends earlier: shortens
        (date(2026, 11, 21), date(2026, 11, 21)),  # strictly inside
        (date(2026, 11, 22), date(2026, 11, 25)),  # partial overlap, later start
    ],
)
def test_trip_may_not_shrink_or_start_later(start: date, end: date) -> None:
    make()
    before = fp.add_trip("iv", date(2026, 11, 20), date(2026, 11, 22), now=at(10, 9))
    with pytest.raises(ValueError, match=r"stricter|cover"):
        fp.add_trip("iv", start, end, now=at(11, 9))
    assert fp.list_projects() == [before]


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (date(2026, 11, 20), date(2026, 11, 19)),
        (date(2026, 11, 28), date(2026, 11, 29)),
    ],
)
def test_bad_trip_ranges(start: date, end: date) -> None:
    make()
    with pytest.raises(ValueError):  # noqa: PT011
        fp.add_trip("iv", start, end, now=at(10, 9))


def test_trip_on_wrong_project() -> None:
    with pytest.raises(KeyError):
        fp.add_trip("ghost", date(2026, 11, 20), date(2026, 11, 21), now=at(10, 9))
    fp.create_project(
        "f",
        name="F",
        start=date(2026, 12, 1),
        end=date(2026, 12, 3),
        replaces=["leetcode"],
        daily_minutes=30,
        unlock_minutes=10,
    )
    with pytest.raises(ValueError, match="interview"):
        fp.add_trip("f", date(2026, 12, 2), date(2026, 12, 3), now=at(10, 9))


def test_answer_false_to_true_ok_true_to_false_refused() -> None:
    make()
    fp.answer_weekend("iv", SAT1, trip=False, now=at(11, 9))
    yes = fp.answer_weekend("iv", SAT1, trip=True, now=at(11, 10))
    assert dict(yes.weekend_answers) == {SAT1: True}
    with pytest.raises(ValueError, match="stricter"):
        fp.answer_weekend("iv", SAT1, trip=False, now=at(11, 11))
    assert dict(fp.list_projects()[0].weekend_answers) == {SAT1: True}


def test_repeating_an_answer_writes_no_second_row() -> None:
    make()
    fp.answer_weekend("iv", SAT1, trip=True, now=at(11, 9))
    fp.answer_weekend("iv", SAT1, trip=True, now=at(11, 10))
    rows = [r for r in evidence.read("iv") if r.milestone == "trip_ask:2026-11-14"]
    assert [(r.kind, r.value) for r in rows] == [("answer", True)]


@pytest.mark.parametrize(
    "day", [date(2026, 11, 15), date(2026, 11, 7), date(2026, 11, 28)]
)
def test_answer_only_for_a_weekend_of_the_project(day: date) -> None:
    make()
    with pytest.raises(ValueError, match="weekend"):
        fp.answer_weekend("iv", day, trip=True, now=at(11, 9))


def test_no_trip_answer_contradicting_an_explicit_trip_is_refused() -> None:
    make()
    fp.add_trip("iv", date(2026, 11, 13), date(2026, 11, 15), now=at(10, 9))
    with pytest.raises(ValueError, match="trip covers"):
        fp.answer_weekend("iv", SAT1, trip=False, now=at(11, 9))


def test_late_answer_unlocks_but_is_late_done() -> None:
    p = make()
    assert states(p, at(13, 8))["trip_ask:2026-11-14"] == "missed"
    p = fp.answer_weekend("iv", SAT1, trip=False, now=at(13, 8))
    assert states(p, at(13, 9))["trip_ask:2026-11-14"] == "late_done"


def test_answer_on_wrong_project() -> None:
    with pytest.raises(KeyError):
        fp.answer_weekend("ghost", SAT1, trip=True, now=at(11, 9))


def test_find_skips_other_projects() -> None:
    fp.create_project(
        "f",
        name="F",
        start=date(2026, 10, 1),
        end=date(2026, 10, 3),
        replaces=["leetcode"],
        daily_minutes=30,
        unlock_minutes=10,
    )
    make()
    p = fp.answer_weekend("iv", SAT1, trip=True, now=at(11, 9))
    assert dict(p.weekend_answers) == {SAT1: True}


def test_late_no_trip_answer_cannot_erase_an_overdue_phone_milestone() -> None:
    make()
    assert states(fp.list_projects()[0], at(13, 13))["phone:2026-11-14"] == "missed"
    p = fp.answer_weekend("iv", SAT1, trip=False, now=at(13, 13))
    got = states(p, at(13, 14))
    assert got["trip_ask:2026-11-14"] == "late_done"
    assert got["phone:2026-11-14"] == "missed"


def test_no_trip_answer_before_the_phone_is_due_drops_it() -> None:
    make()
    p = fp.answer_weekend("iv", SAT1, trip=False, now=at(13, 11, 59))
    assert "phone:2026-11-14" not in states(p, at(13, 14))


def test_no_trip_answer_given_at_creation_has_no_phone() -> None:
    p = make(weekend_answers={SAT1: False})
    got = states(p, at(13, 14))
    assert got["trip_ask:2026-11-14"] == "done"
    assert "phone:2026-11-14" not in got
