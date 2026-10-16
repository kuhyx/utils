# Copyright (c) 2026 Krzysztof Rudnicki
"""A date is never in both pools: the lazy free-day check and its mirror."""

from __future__ import annotations

from datetime import date
import sys
import types
from typing import TYPE_CHECKING

import pytest

from sickdays._api import add_sick_day
from sickdays._conflict import ensure_not_free, ensure_not_sick, free_day_predicate
from sickdays._errors import (
    ConflictCheckUnavailableError,
    FreeDayConflictError,
    SickDayConflictError,
)
from sickdays._paths import Paths

if TYPE_CHECKING:
    from pathlib import Path

TODAY = date(2026, 10, 16)


def test_the_predicate_is_freedays_own(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = types.ModuleType("freedays")

    def _is_free_day(day: date) -> bool:
        return day == TODAY

    vars(fake)["is_free_day"] = _is_free_day
    monkeypatch.setitem(sys.modules, "freedays", fake)
    predicate = free_day_predicate()
    assert predicate(TODAY)
    assert not predicate(date(2026, 10, 17))


def test_no_freedays_means_the_add_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "freedays", None)
    with pytest.raises(ConflictCheckUnavailableError, match="not installed"):
        free_day_predicate()


def test_ensure_not_free_passes_a_normal_day() -> None:
    ensure_not_free(TODAY, lambda _day: False)
    with pytest.raises(FreeDayConflictError, match="freedays release"):
        ensure_not_free(TODAY, lambda _day: True)


def test_a_sick_day_cannot_be_marked_free() -> None:
    ensure_not_sick(TODAY)
    add_sick_day(TODAY, now=TODAY)
    with pytest.raises(SickDayConflictError, match="sickdays remove"):
        ensure_not_sick(TODAY)


def test_ensure_not_sick_honours_explicit_paths(tmp_path: Path) -> None:
    elsewhere = Paths.under(tmp_path / "elsewhere")
    add_sick_day(TODAY, paths=elsewhere, now=TODAY)
    ensure_not_sick(TODAY)
    with pytest.raises(SickDayConflictError):
        ensure_not_sick(TODAY, paths=elsewhere)
