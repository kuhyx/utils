"""Date handling: the one place allowed an opinion about "today"."""

from __future__ import annotations

from datetime import date

import pytest

from freedays._day import parse_iso, resolve, to_iso, today


def test_today_reads_the_clock_when_not_overridden() -> None:
    assert isinstance(today(), date)


def test_today_returns_the_override_untouched() -> None:
    fixed = date(2026, 3, 4)
    assert today(fixed) == fixed


def test_parse_iso_round_trips() -> None:
    assert to_iso(parse_iso("2026-12-24")) == "2026-12-24"


def test_parse_iso_tolerates_surrounding_whitespace() -> None:
    assert parse_iso("  2026-12-24 ") == date(2026, 12, 24)


@pytest.mark.parametrize("bad", ["24-12-2026", "2026-13-01", "tomorrow", ""])
def test_parse_iso_rejects_junk_and_names_it(bad: str) -> None:
    with pytest.raises(ValueError, match="not a YYYY-MM-DD date"):
        parse_iso(bad)


def test_resolve_understands_today() -> None:
    assert resolve("today", now=date(2026, 3, 4)) == date(2026, 3, 4)


def test_resolve_understands_tomorrow_across_a_month_boundary() -> None:
    assert resolve("TOMORROW", now=date(2026, 3, 31)) == date(2026, 4, 1)


def test_resolve_falls_through_to_a_plain_date() -> None:
    assert resolve("2026-12-24", now=date(2026, 3, 4)) == date(2026, 12, 24)


def test_resolve_rejects_junk() -> None:
    with pytest.raises(ValueError, match="not a YYYY-MM-DD date"):
        resolve("next tuesday", now=date(2026, 3, 4))
