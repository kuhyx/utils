"""The progress row every review credit is written with (earned_time 0.24.0)."""

from __future__ import annotations

import datetime as dt
import importlib
import json
import logging
from pathlib import Path
import tempfile
from typing import TYPE_CHECKING, Any

import pytest

from leetcode_coach import review_ledger
from leetcode_coach.tests._review_support import REVIEW_KEY

if TYPE_CHECKING:
    from types import ModuleType

TZ = dt.timezone(dt.timedelta(hours=1))
MONDAY = dt.datetime(2026, 11, 23, 9, 0, 0, tzinfo=TZ)
TUESDAY = dt.datetime(2026, 11, 24, 9, 0, 0, tzinfo=TZ)
REPO_ROOT = Path(__file__).resolve().parents[3]


def _rows() -> list[dict[str, Any]]:
    data = json.loads(review_ledger.LEDGER_PATH.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = data["entries"]
    return rows


def _ids() -> list[str]:
    return [row["entry_id"] for row in _rows()]


def _progress_ids() -> list[str]:
    return [i for i in _ids() if i.startswith("progress:")]


def _finish(slug: str, due: int, now: dt.datetime = MONDAY) -> bool:
    return review_ledger.record(slug, "debugging", due=due, now=now)


def _signed(row: dict[str, object]) -> dict[str, object]:
    return {**row, "hmac": review_ledger.entry_signature(row, REVIEW_KEY)}


def _foreign_progress(
    source: str, target: str, day: str = "2026-11-23"
) -> dict[str, object]:
    return {
        "entry_id": f"progress:{day}:0:{target}",
        "kind": "progress",
        "day": day,
        "created_at": f"{day}T08:00:00+01:00",
        "amount": 0,
        "device": "pc",
        "detail": {"source": source, "for_day": day, "done": "0", "target": target},
    }


def test_the_first_review_of_a_day_writes_its_credit_and_progress_one_of_due() -> None:
    assert _finish("two-sum", due=3) is True
    credit, progress = _rows()
    assert credit["entry_id"] == "review:two-sum"
    progress.pop("hmac")
    assert progress == {
        "entry_id": "progress:2026-11-23:1:3",
        "kind": "progress",
        "day": "2026-11-23",
        "created_at": "2026-11-23T09:00:00+01:00",
        "amount": 0,
        "device": "pc",
        "detail": {
            "source": "review",
            "for_day": "2026-11-23",
            "done": "1",
            "target": "3",
        },
    }


def test_the_second_review_reuses_the_frozen_target_whatever_is_due_now() -> None:
    _finish("two-sum", due=3)
    _finish("3sum", due=1)
    assert _progress_ids() == ["progress:2026-11-23:1:3", "progress:2026-11-23:2:3"]
    _finish("lru-cache", due=9)
    assert _progress_ids()[-1] == "progress:2026-11-23:3:3"


def test_a_repeat_of_the_same_state_writes_nothing() -> None:
    _finish("two-sum", due=3)
    before = review_ledger.LEDGER_PATH.read_bytes()
    assert _finish("two-sum", due=2) is False
    assert review_ledger.LEDGER_PATH.read_bytes() == before


def test_done_is_capped_at_the_target_and_adds_no_row_past_it() -> None:
    _finish("a", due=1)
    _finish("b", due=1)
    assert _progress_ids() == ["progress:2026-11-23:1:1"]
    assert _ids().count("review:b") == 1


def test_a_new_day_freezes_its_own_target() -> None:
    _finish("a", due=3)
    _finish("b", due=3)
    _finish("c", due=2, now=TUESDAY)
    assert _progress_ids() == [
        "progress:2026-11-23:1:3",
        "progress:2026-11-23:2:3",
        "progress:2026-11-24:1:2",
    ]


def test_a_credit_with_no_progress_gets_it_on_the_next_call() -> None:
    """Rows from before the progress writer: done counts them, target is due."""
    credit = _signed(
        {
            "entry_id": "review:old",
            "kind": "credit",
            "day": "2026-11-23",
            "created_at": "2026-11-23T08:00:00+01:00",
            "amount": 1,
            "device": "pc",
            "detail": {
                "title_slug": "old",
                "cause": "statement",
                "source": review_ledger.SOURCE,
                "finished_at": "1",
            },
        }
    )
    review_ledger.LEDGER_PATH.parent.mkdir(parents=True)
    review_ledger.LEDGER_PATH.write_text(
        json.dumps({"version": 1, "entries": [credit]}), encoding="utf-8"
    )
    assert _finish("old", due=2) is False
    assert _progress_ids() == ["progress:2026-11-23:1:2"]
    _finish("new", due=1)
    assert _progress_ids()[-1] == "progress:2026-11-23:2:2"


@pytest.mark.parametrize(
    ("source", "signed"),
    [("review", False), ("workout", True), ("leetcode", True)],
)
def test_only_a_signed_review_progress_row_freezes_the_target(
    source: str, *, signed: bool
) -> None:
    other = _foreign_progress(source, "99")
    row = _signed(other) if signed else {**other, "hmac": "0" * 64}
    review_ledger.LEDGER_PATH.parent.mkdir(parents=True)
    review_ledger.LEDGER_PATH.write_text(
        json.dumps({"version": 1, "entries": [row]}), encoding="utf-8"
    )
    _finish("two-sum", due=3)
    assert _progress_ids()[-1] == "progress:2026-11-23:1:3"


def test_every_row_verifies_with_earned_time_and_the_credit_comes_with_progress(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(REPO_ROOT / "earned_time"))
    earned_time: ModuleType = importlib.import_module("earned_time")
    _finish("a", due=2)
    _finish("b", due=2)
    rows = _rows()
    assert [r["kind"] for r in rows] == ["credit", "progress", "credit", "progress"]
    assert all(earned_time.verified(r, REVIEW_KEY) for r in rows)
    assert all(r["hmac"] == earned_time.entry_signature(r, REVIEW_KEY) for r in rows)
    assert all(isinstance(v, str) for r in rows[1::2] for v in r["detail"].values())


def test_a_failed_write_leaves_neither_row_and_is_logged_loudly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    blocker = tmp_path / "a-file"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(review_ledger, "LEDGER_PATH", blocker / "review_ledger.json")
    with caplog.at_level(logging.WARNING), pytest.raises(review_ledger.LedgerError):
        _finish("two-sum", due=3)
    assert any(r.levelno >= logging.WARNING for r in caplog.records)
    assert not (blocker / "review_ledger.json").exists()


def test_the_failed_second_review_leaves_the_first_pair_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _finish("a", due=2)
    before = review_ledger.LEDGER_PATH.read_bytes()

    def boom(*_a: object, **_k: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(tempfile, "mkstemp", boom)
    with pytest.raises(review_ledger.LedgerError):
        _finish("b", due=2)
    assert review_ledger.LEDGER_PATH.read_bytes() == before


@pytest.mark.parametrize("due", [-1, 0])
def test_a_first_review_with_nothing_due_still_gets_a_target_of_one(due: int) -> None:
    _finish("two-sum", due=due)
    assert _progress_ids() == ["progress:2026-11-23:1:1"]
