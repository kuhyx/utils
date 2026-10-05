# Copyright (c) 2026 Krzysztof Rudnicki
"""The registry: earner arithmetic and each gate's credit rule."""

from __future__ import annotations

from datetime import UTC, date, datetime
import logging
from typing import TYPE_CHECKING

import pytest

from earned_time import (
    ANKI,
    AUTOMATION,
    EARNERS,
    LEETCODE,
    READING,
    WORKOUT,
    earner,
)
from earned_time._ledger import today_window

if TYPE_CHECKING:
    from collections.abc import Mapping

    from earned_time import Earner

NOON = datetime(2026, 10, 4, 12, tzinfo=UTC)
WINDOW = today_window(NOON)
INSIDE = WINDOW[1] - 60
BEFORE = WINDOW[0] - 60
TODAY = datetime.fromtimestamp(WINDOW[0]).astimezone().date().isoformat()


def test_registry_order_and_names() -> None:
    assert [e.name for e in EARNERS] == [
        "workout",
        "leetcode",
        "reading",
        "anki",
        "automation",
    ]


def test_lookup_by_name() -> None:
    assert earner("reading") is READING


def test_lookup_unknown_raises() -> None:
    with pytest.raises(KeyError):
        earner("nope")


def test_penalty_starts_on_its_day() -> None:
    assert not READING.penalised_on(date(2026, 9, 30))
    assert READING.penalised_on(date(2026, 10, 1))
    assert not LEETCODE.penalised_on(date(2030, 1, 1))


def test_flat_earner_pays_once() -> None:
    assert [LEETCODE.gaming_for(n) for n in range(3)] == [0, 60, 60]
    assert [LEETCODE.shutdown_for(n) for n in range(3)] == [0, 60, 60]


def test_counted_earner_pays_each_extra_unit_in_shutdown_only() -> None:
    assert [WORKOUT.shutdown_for(n) for n in range(4)] == [0, 120, 180, 240]
    assert [WORKOUT.gaming_for(n) for n in range(3)] == [0, 120, 120]


def _match(e: object, row: Mapping[str, object]) -> bool:
    fn = getattr(e, "match", None)
    assert fn is not None
    return bool(fn(dict(row), WINDOW))


@pytest.mark.parametrize(
    ("detail", "day", "expected"),
    [
        ({"submitted_at": str(INSIDE)}, "1999-01-01", True),
        ({"submitted_at": BEFORE}, TODAY, False),
        ({}, TODAY, True),
        (None, TODAY, True),
        (None, "1999-01-01", False),
    ],
)
def test_leetcode_match(detail: object, day: str, *, expected: bool) -> None:
    assert _match(LEETCODE, {"detail": detail, "day": day}) is expected


def test_leetcode_unparsable_stamp_falls_back_to_day(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        row = {"detail": {"submitted_at": "soon"}, "day": TODAY, "entry_id": "x"}
        assert _match(LEETCODE, row)
    assert "unparsable submitted_at" in caplog.text


@pytest.mark.parametrize(
    ("detail", "expected"),
    [
        ({"bonus": "1", "ended_at": INSIDE}, True),
        ({"bonus": "1", "ended_at": BEFORE}, False),
        ({"bonus": "0", "ended_at": INSIDE}, False),
        ("not a dict", False),
    ],
)
def test_reading_match(detail: object, *, expected: bool) -> None:
    assert _match(READING, {"detail": detail}) is expected


def test_reading_unusable_end_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        assert not _match(READING, {"detail": {"bonus": "1"}, "entry_id": "r"})
    assert "no usable ended_at" in caplog.text


@pytest.mark.parametrize(
    ("detail", "expected"),
    [
        ({"anki_day": TODAY}, True),
        ({"anki_day": "2026-10-03"}, False),
        ({}, False),
        ("not a dict", False),
    ],
)
@pytest.mark.parametrize("anki_earner", [ANKI, AUTOMATION])
def test_anki_match(anki_earner: Earner, detail: object, *, expected: bool) -> None:
    assert _match(anki_earner, {"detail": detail}) is expected


def test_anki_penalty_starts_the_day_after_it_shipped() -> None:
    # Shipped 2026-10-05: that day is a pure bonus, never an unearnable cut.
    assert not ANKI.penalised_on(date(2026, 10, 5))
    assert ANKI.penalised_on(date(2026, 10, 6))


def test_automation_reads_its_own_ledger() -> None:
    # One file per anki-guard quota, so the two earners never share a credit.
    assert AUTOMATION.ledger != ANKI.ledger
    assert AUTOMATION.ledger == ".local/share/anki_guard/automation_ledger.json"


def test_automation_penalty_starts_the_day_after_the_import() -> None:
    # The deck reached the sync server 2026-10-05: no cut before it is studiable.
    assert not AUTOMATION.penalised_on(date(2026, 10, 5))
    assert AUTOMATION.penalised_on(date(2026, 10, 6))
