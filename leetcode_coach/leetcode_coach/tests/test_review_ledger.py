"""The coach's own signed review ledger: one row per finished review."""

from __future__ import annotations

import datetime as dt
import importlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from leetcode_coach import review_ledger
from leetcode_coach.tests._review_support import (
    REAL_KEY_FILE,
    REAL_REVIEW_LEDGER,
    REVIEW_KEY,
)

if TYPE_CHECKING:
    from types import ModuleType

NOW = dt.datetime(
    2026, 11, 21, 22, 5, 7, 123456, tzinfo=dt.timezone(dt.timedelta(hours=1))
)
REPO_ROOT = Path(__file__).resolve().parents[3]
# A real guard row (jq -c '.entries[-3]' of the guard ledger, 2026-11-21).
GUARD_ROW: dict[str, object] = {
    "entry_id": "ac:2200718614",
    "kind": "credit",
    "day": "2026-11-21",
    "created_at": "2026-11-21T18:01:58.572372+01:00",
    "amount": 1,
    "device": "pc",
    "detail": {
        "title_slug": "matrix-diagonal-sum",
        "lang": "typescript",
        "source": "leetcode",
        "submitted_at": "1795280494",
    },
    "hmac": "f47d870875b9adcbc1fa4982ac56caf85fb1e206b2073fedba471694b84393ac",
}


def _ledger() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        review_ledger.LEDGER_PATH.read_text(encoding="utf-8")
    )
    return data


def _earned_time(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """The monorepo's own earned_time: the reader that must accept our rows."""
    monkeypatch.syspath_prepend(str(REPO_ROOT / "earned_time"))
    return importlib.import_module("earned_time")


def test_the_seams_point_away_from_the_real_machine(tmp_path: Path) -> None:
    assert tmp_path in review_ledger.LEDGER_PATH.parents
    assert tmp_path in review_ledger.KEY_FILE.parents
    home = Path.home() / ".local" / "share" / "leetcode-coach"
    assert home / "review_ledger.json" == REAL_REVIEW_LEDGER
    assert Path("/etc/workout-locker/hmac.key") == REAL_KEY_FILE


def test_a_finished_review_writes_one_signed_row_in_the_guard_layout() -> None:
    assert review_ledger.record("two-sum", "idea-to-code", due=1, now=NOW) is True
    data = _ledger()
    assert list(data) == ["version", "entries"]
    assert data["version"] == 1
    row, progress = data["entries"]
    assert progress["entry_id"] == "progress:2026-11-21:1:1"
    signature = row.pop("hmac")
    assert row == {
        "entry_id": "review:two-sum",
        "kind": "credit",
        "day": "2026-11-21",
        "created_at": "2026-11-21T22:05:07.123456+01:00",
        "amount": 1,
        "device": "pc",
        "detail": {
            "title_slug": "two-sum",
            "cause": "idea-to-code",
            "source": "leetcode-coach-review",
            "finished_at": str(int(NOW.timestamp())),
        },
    }
    assert signature == review_ledger.entry_signature(row, REVIEW_KEY)
    assert [p.name for p in review_ledger.LEDGER_PATH.parent.iterdir()] == [
        "review_ledger.json"
    ]


def test_earned_time_verifies_the_row_and_signs_it_the_same(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    earned_time = _earned_time(monkeypatch)
    review_ledger.record("two-sum", "missing-idea", due=1, now=NOW)
    row, _progress = _ledger()["entries"]
    assert earned_time.verified(row, REVIEW_KEY) is True
    assert row["hmac"] == earned_time.entry_signature(row, REVIEW_KEY)
    odd = {**GUARD_ROW, "detail": {"title_slug": "zażółć", "n": 1.5, "x": None}}
    for sample in (GUARD_ROW, odd):
        assert review_ledger.entry_signature(
            sample, REVIEW_KEY
        ) == earned_time.entry_signature(sample, REVIEW_KEY)
    forged = {**row, "amount": 2}
    assert earned_time.verified(forged, REVIEW_KEY) is False


def test_the_default_clock_is_local_time_with_an_offset() -> None:
    review_ledger.record("two-sum", "debugging", due=1)
    row, _progress = _ledger()["entries"]
    created = dt.datetime.fromisoformat(row["created_at"])
    assert created.utcoffset() is not None
    assert row["day"] == created.date().isoformat()
    assert row["detail"]["finished_at"] == str(int(created.timestamp()))


def test_a_slug_is_never_written_twice() -> None:
    assert review_ledger.record("two-sum", "debugging", due=1, now=NOW) is True
    before = review_ledger.LEDGER_PATH.read_bytes()
    assert review_ledger.record("two-sum", "statement", due=1, now=NOW) is False
    assert review_ledger.LEDGER_PATH.read_bytes() == before
    assert review_ledger.record("3sum", "statement", due=1, now=NOW) is True
    assert [e["entry_id"] for e in _ledger()["entries"] if e["kind"] == "credit"] == [
        "review:two-sum",
        "review:3sum",
    ]


@pytest.mark.parametrize("content", [None, b"", b"  \n"])
def test_without_a_key_nothing_is_written(content: bytes | None) -> None:
    if content is None:
        review_ledger.KEY_FILE.unlink()
    else:
        review_ledger.KEY_FILE.write_bytes(content)
    with pytest.raises(review_ledger.LedgerError, match="signing key"):
        review_ledger.record("two-sum", "debugging", due=1, now=NOW)
    assert not review_ledger.LEDGER_PATH.exists()


@pytest.mark.parametrize("text", ["not json", '{"entries": 5}', "[]", "\xff"])
def test_an_unreadable_ledger_is_never_overwritten(text: str) -> None:
    review_ledger.LEDGER_PATH.parent.mkdir(parents=True)
    review_ledger.LEDGER_PATH.write_bytes(text.encode("latin-1"))
    with pytest.raises(review_ledger.LedgerError, match="not overwritten"):
        review_ledger.record("two-sum", "debugging", due=1, now=NOW)
    assert review_ledger.LEDGER_PATH.read_bytes() == text.encode("latin-1")


def test_a_failed_write_is_a_ledger_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blocker = tmp_path / "a-file"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(review_ledger, "LEDGER_PATH", blocker / "review_ledger.json")
    with pytest.raises(review_ledger.LedgerError, match="cannot write"):
        review_ledger.record("two-sum", "debugging", due=1, now=NOW)
