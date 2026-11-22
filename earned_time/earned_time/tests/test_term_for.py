# Copyright (c) 2026 Krzysztof Rudnicki
"""``term_for``: the one place an earner's pay for a day is derived.

``resolve`` builds its terms through it, so a consumer pricing one earner (the
screen-locker's live pass) can never disagree with ``resolve``.
"""

from __future__ import annotations

from datetime import date
from itertools import product
from typing import Any

import pytest

from earned_time import (
    LEETCODE,
    REVIEW,
    REVIEW_PROGRESS_FROM,
    WORKOUT,
    Earner,
    Progress,
    Term,
    earners_for,
    resolve,
    shutdown_minutes_for,
    term_for,
)

DAYS = (
    date(2026, 10, 5),
    date(2026, 10, 16),
    date(2026, 11, 22),
    REVIEW_PROGRESS_FROM.replace(day=REVIEW_PROGRESS_FROM.day - 1),
    REVIEW_PROGRESS_FROM,
    REVIEW_PROGRESS_FROM.replace(day=REVIEW_PROGRESS_FROM.day + 1),
    date(2027, 1, 1),
)
ANSWERS: tuple[int | bool | None, ...] = (True, False, None, 0, 1, 2)
FACTS: tuple[Progress | None, ...] = (
    None,
    Progress(0, 3),
    Progress(1, 3),
    Progress(2, 3),
    Progress(3, 3),
    Progress(1, 1),
    Progress(7, 2),
)
LADDER = date(2026, 11, 22)


def test_the_signature_is_keyword_clear() -> None:
    loose: Any = term_for
    with pytest.raises(TypeError):
        loose(LEETCODE, LADDER, 1)


@pytest.mark.parametrize("day", DAYS)
def test_term_for_equals_the_term_resolve_builds(day: date) -> None:
    for item, answer, fact in product(earners_for(day), ANSWERS, FACTS):
        others = {e.name: 0 for e in earners_for(day)}
        asked = resolve(
            {**others, item.name: answer},
            day,
            progress=None if fact is None else {item.name: fact},
        ).term(item.name)
        got = term_for(item, day, answer=answer, progress=fact)
        assert got == asked, (item.name, day, answer, fact)
        assert isinstance(got, Term)


def test_a_generic_earner_pays_a_share_of_the_ladder_rung() -> None:
    full = shutdown_minutes_for(LEETCODE, LADDER)
    assert full == 60
    row = Progress(1, 3)
    assert term_for(LEETCODE, LADDER, answer=False, progress=row).shutdown_minutes == 20
    assert term_for(LEETCODE, LADDER, answer=False, progress=row).gaming_minutes == 20
    assert term_for(LEETCODE, LADDER, answer=False).shutdown_minutes == 0


def test_a_yes_pays_full_whatever_the_row_says() -> None:
    low = term_for(LEETCODE, LADDER, answer=True, progress=Progress(1, 3))
    assert low.shutdown_minutes == shutdown_minutes_for(LEETCODE, LADDER)
    assert low.progress is None


def test_a_row_never_pays_above_full() -> None:
    term = term_for(LEETCODE, LADDER, answer=False, progress=Progress(9, 3))
    assert term.shutdown_minutes == shutdown_minutes_for(LEETCODE, LADDER)


def test_none_earns_nothing_even_with_a_full_row() -> None:
    assert term_for(LEETCODE, LADDER, answer=None, progress=Progress(3, 3)) == Term(
        LEETCODE, None, 0, 0
    )


def test_the_review_follows_its_dated_rule() -> None:
    row = Progress(1, 3)
    before = REVIEW_PROGRESS_FROM.replace(day=REVIEW_PROGRESS_FROM.day - 1)
    assert term_for(REVIEW, before, answer=True, progress=row).shutdown_minutes == 20
    assert term_for(REVIEW, before, answer=False, progress=row).shutdown_minutes == 0
    on = REVIEW_PROGRESS_FROM
    assert term_for(REVIEW, on, answer=True, progress=row).shutdown_minutes == 6
    assert term_for(REVIEW, on, answer=True).shutdown_minutes == 0
    assert term_for(REVIEW, on, answer=False, progress=row).shutdown_minutes == 0


def test_a_counted_earner_pays_per_unit() -> None:
    day = LADDER
    one = term_for(WORKOUT, day, answer=1).shutdown_minutes
    assert term_for(WORKOUT, day, answer=True).shutdown_minutes == one
    assert term_for(WORKOUT, day, answer=0).shutdown_minutes == 0


def _expected(
    item: Earner, day: date, answer: int | None, fact: Progress | None
) -> int:
    """The shutdown minutes by the written rules, not by the library's code."""
    if answer is None:
        return 0
    full = shutdown_minutes_for(item, day)
    yes = answer is True or answer >= 1
    if item is REVIEW and day >= REVIEW_PROGRESS_FROM:
        if not yes or fact is None:
            return 0
        return full * min(fact.done, fact.target) // fact.target
    if yes or (item is REVIEW) or fact is None:
        return item.shutdown_for(max(0, int(answer)), day)
    return full * min(fact.done, fact.target) // fact.target


@pytest.mark.parametrize("day", DAYS)
def test_the_minutes_follow_the_written_rules(day: date) -> None:
    for item, answer, fact in product(earners_for(day), ANSWERS, FACTS):
        got = term_for(item, day, answer=answer, progress=fact)
        assert got.shutdown_minutes == _expected(item, day, answer, fact), (
            item.name,
            day,
            answer,
            fact,
        )
