# Copyright (c) 2026 Krzysztof Rudnicki
"""``evening_chain pending``: which rungs are unpaid, and its exit code."""

from __future__ import annotations

from typing import TYPE_CHECKING

from gatelock import RANK_DIET_GUARD, RANK_SCREEN_LOCKER
from gatelock import evening_chain as chain
from gatelock._arbiter import RANK_EVENING_GATE
from gatelock.tests.test_evening_rows import (
    DAY,
    EVENING,
    LATE,
    leetcode_row,
    mark_free,
    mark_sick,
    pay_all,
    seeded,
    tutor_row,
    write_ledger,
)

if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path

    import pytest


def _run(sources: chain.Sources, now: datetime) -> tuple[int, str]:
    out: list[str] = []
    code = chain.pending(sources, lambda: now, out.append)
    return code, " ".join(out)


def test_constants_follow_the_contract() -> None:
    assert chain.EXIT_END_EVENING == 10
    assert chain.EXIT_NO_X == 3
    assert chain.CHAIN == ("reading", "tutor", "leetcode")
    assert chain.CUTOFF.hour == 23


def test_evening_gate_ranks_between_diet_guard_and_screen_locker() -> None:
    assert RANK_EVENING_GATE == 150
    assert RANK_DIET_GUARD < RANK_EVENING_GATE < RANK_SCREEN_LOCKER


def test_nothing_paid_lists_every_rung_exit_0(tmp_path: Path) -> None:
    sources = seeded(tmp_path)
    write_ledger(sources, "reading", [])
    write_ledger(sources, "tutor", [])
    write_ledger(sources, "leetcode", [])
    assert _run(sources, EVENING) == (0, "reading tutor leetcode")


def test_everything_paid_is_exit_1(tmp_path: Path) -> None:
    sources = seeded(tmp_path)
    pay_all(sources)
    assert _run(sources, EVENING) == (1, "")


def test_paid_rungs_are_skipped(tmp_path: Path) -> None:
    sources = seeded(tmp_path)
    pay_all(sources)
    write_ledger(sources, "tutor", [tutor_row(14)])  # 14 min < the 15 quota
    assert _run(sources, EVENING) == (0, "tutor")


def test_tutor_is_quota_based_not_done_today(tmp_path: Path) -> None:
    sources = seeded(tmp_path)
    pay_all(sources)
    write_ledger(sources, "tutor", [tutor_row(15)])
    assert _run(sources, EVENING)[0] == 1
    write_ledger(sources, "tutor", [tutor_row(1)])
    assert _run(sources, EVENING) == (0, "tutor")


def test_free_day_stands_down(tmp_path: Path) -> None:
    sources = seeded(tmp_path)
    mark_free(sources)
    assert _run(sources, EVENING) == (1, "")


def test_sick_day_stands_down(tmp_path: Path) -> None:
    sources = seeded(tmp_path)
    mark_sick(sources)
    assert _run(sources, EVENING) == (1, "")


def test_from_23_00_nothing_is_pending(tmp_path: Path) -> None:
    sources = seeded(tmp_path)
    assert _run(sources, LATE) == (1, "")


def test_unreadable_ledger_fails_closed(tmp_path: Path) -> None:
    sources = seeded(tmp_path)
    pay_all(sources)
    path = write_ledger(sources, "leetcode", [leetcode_row()])
    path.write_text("{not json", encoding="utf-8")
    assert _run(sources, EVENING) == (2, "")


def test_missing_key_fails_closed(tmp_path: Path) -> None:
    sources = seeded(tmp_path)
    pay_all(sources)
    sources.key_file.unlink()
    assert _run(sources, EVENING)[0] == 2


def test_unreadable_rung_wins_over_unpaid_one(tmp_path: Path) -> None:
    sources = seeded(tmp_path)
    write_ledger(sources, "reading", [])
    write_ledger(sources, "leetcode", [leetcode_row()]).write_text("x")
    assert _run(sources, EVENING)[0] == 2


def test_exception_in_the_check_is_exit_2_and_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(_day: object) -> None:
        msg = "registry exploded"
        raise RuntimeError(msg)

    monkeypatch.setattr("earned_time.earners_for", boom)
    code = chain.main(["pending"], sources=seeded(tmp_path), clock=lambda: EVENING)
    assert code == 2
    assert "registry exploded" in capsys.readouterr().err


def test_main_pending_prints_rungs_on_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sources = seeded(tmp_path)
    pay_all(sources)
    write_ledger(sources, "reading", [])
    assert chain.main(["pending"], sources=sources, clock=lambda: EVENING) == 0
    assert capsys.readouterr().out.strip() == "reading"


def test_a_reader_that_raises_is_unchecked_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sources = seeded(tmp_path)
    pay_all(sources)

    def boom(*_args: object, **_kwargs: object) -> None:
        msg = "no shared reader"
        raise ValueError(msg)

    monkeypatch.setattr("earned_time.done_today", boom)
    assert _run(sources, EVENING) == (2, "")


def test_a_rung_the_registry_dropped_is_not_asked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import earned_time

    sources = seeded(tmp_path)
    write_ledger(sources, "leetcode", [])
    kept = tuple(e for e in earned_time.earners_for(DAY) if e.name != "reading")
    monkeypatch.setattr("earned_time.earners_for", lambda _day: kept)
    assert _run(sources, EVENING) == (0, "tutor leetcode")
