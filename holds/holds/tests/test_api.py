# Copyright (c) 2026 Krzysztof Rudnicki
"""Contract tests for the public ``holds`` API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import logging
from typing import TYPE_CHECKING

import pytest

import holds

if TYPE_CHECKING:
    from pathlib import Path

NOW = datetime(2026, 11, 3, 21, 0)
WED = datetime(2026, 11, 4, 17, 0)
WED_END = datetime(2026, 11, 4, 20, 0)
REASON = "HackerRank proctored test"


def _real(delta: timedelta) -> datetime:
    """A whole-minute moment ``delta`` from the real clock."""
    return (datetime.now() + delta).replace(second=0, microsecond=0)


def _seed(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"holds": rows}), encoding="utf-8")


def _row(start: str, end: str, hid: str = "a") -> dict[str, str]:
    return {
        "id": hid,
        "start": start,
        "end": end,
        "reason": "some long reason",
        "created": "2026-11-01T10:00:00",
    }


def test_add_then_active_half_open(data_file: Path) -> None:
    hold = holds.add(WED, WED_END, REASON, now=NOW)
    assert hold.id == "20261104T1700-hackerrank-proctored-test"
    assert hold.created == NOW
    assert holds.active(WED - timedelta(minutes=1)) is None
    assert holds.active(WED) == hold
    assert holds.active(datetime(2026, 11, 4, 19, 59)) == hold
    assert holds.active(WED_END) is None
    stored = json.loads(data_file.read_text(encoding="utf-8"))
    assert stored["holds"][0]["start"] == "2026-11-04T17:00"
    assert stored["holds"][0]["created"] == "2026-11-03T21:00:00"


def test_covers_ignores_gate_in_v1() -> None:
    holds.add(WED, WED_END, REASON, now=NOW)
    assert holds.covers("focus-guard", WED) is True
    assert holds.covers("diet-guard", WED_END) is False


def test_active_defaults_to_real_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    assert holds.active() is None
    assert holds.next_change() is None
    assert holds.covers("x") is False
    with pytest.raises(holds.HoldsError, match="30 min"):
        holds.add(_real(timedelta(minutes=5)), _real(timedelta(hours=1)), REASON)


def test_aware_datetimes_become_local_naive() -> None:
    aware = WED.astimezone().astimezone(UTC)
    hold = holds.add(
        aware, aware + timedelta(hours=3), REASON, now=NOW.astimezone().astimezone(UTC)
    )
    assert hold.start == WED
    assert holds.active(aware + timedelta(hours=1)) == hold


def test_next_change_start_end_none() -> None:
    first = holds.add(WED, WED_END, REASON, now=NOW)
    second = holds.add(
        datetime(2026, 11, 5), datetime(2026, 11, 5, 14, 30), "fallback window", now=NOW
    )
    assert holds.next_change(NOW) == first.start
    assert holds.next_change(WED) == first.end
    assert holds.next_change(WED_END) == second.start
    assert holds.next_change(datetime(2026, 11, 6)) is None


@pytest.mark.parametrize(
    ("start", "end", "reason", "match"),
    [
        (WED, WED + timedelta(hours=15, minutes=1), REASON, "15 h"),
        (WED, WED, REASON, "after start"),
        (NOW + timedelta(minutes=29), NOW + timedelta(hours=2), REASON, "30 min"),
        (WED, WED_END, "too short", "10 char"),
        (WED, WED_END, "   padded   ", "10 char"),
        (WED + timedelta(seconds=5), WED_END, REASON, "whole minutes"),
    ],
)
def test_add_rejects_ratchet_violations(
    start: datetime, end: datetime, reason: str, match: str
) -> None:
    with pytest.raises(holds.HoldsError, match=match):
        holds.add(start, end, reason, now=NOW)
    assert holds.active(start) is None


def test_add_exact_limits_pass() -> None:
    start = NOW + timedelta(minutes=30)
    holds.add(start, start + timedelta(hours=15), REASON, now=NOW)


def test_add_rejects_overlap_but_allows_touching() -> None:
    holds.add(WED, WED_END, REASON, now=NOW)
    for s, e in [
        (WED_END - timedelta(hours=1), WED_END + timedelta(hours=1)),
        (WED - timedelta(hours=1), WED + timedelta(hours=1)),
        (WED + timedelta(minutes=30), WED + timedelta(hours=1)),
    ]:
        with pytest.raises(holds.HoldsError, match="overlap"):
            holds.add(s, e, REASON, now=NOW)
    holds.add(WED_END, WED_END + timedelta(hours=1), REASON, now=NOW)


def test_add_caps_three_per_iso_week_but_not_next_week() -> None:
    for day in (4, 5, 6):
        start = datetime(2026, 11, day, 9)
        holds.add(start, start + timedelta(hours=1), REASON, now=NOW)
    start = datetime(2026, 11, 7, 9)
    with pytest.raises(holds.HoldsError, match="3 holds"):
        holds.add(start, start + timedelta(hours=1), REASON, now=NOW)
    nxt = datetime(2026, 11, 9, 9)  # Monday, ISO week 46
    holds.add(nxt, nxt + timedelta(hours=1), REASON, now=NOW)


def test_remove_only_before_start() -> None:
    hold = holds.add(WED, WED_END, REASON, now=NOW)
    with pytest.raises(holds.HoldsError, match="already started"):
        holds.remove(hold.id, now=WED)
    holds.remove(hold.id, now=NOW)
    assert holds.active(WED) is None
    with pytest.raises(holds.HoldsError, match="unknown"):
        holds.remove(hold.id, now=NOW)


def test_remove_defaults_to_real_clock() -> None:
    start = _real(timedelta(days=1))
    hold = holds.add(start, start + timedelta(hours=1), REASON)
    holds.remove(hold.id)
    assert holds.next_change() is None


def test_ids_stay_unique_and_slug_is_bounded() -> None:
    long_reason = "!!! " + "word " * 30
    first = holds.add(WED, WED_END, long_reason, now=NOW)
    assert len(first.id) <= 60
    assert first.id.startswith("20261104T1700-word-word")
    symbols = holds.add(
        datetime(2026, 11, 5), datetime(2026, 11, 5, 1), "!!!!!!!!!!!!", now=NOW
    )
    assert symbols.id == "20261105T0000-hold"


def test_default_path_under_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("HOLDS_DATA")
    monkeypatch.setenv("HOME", str(tmp_path))
    holds.add(WED, WED_END, REASON, now=NOW)
    assert (tmp_path / ".local/share/holds/holds.json").is_file()


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        "[]",
        '{"holds": {}}',
        '{"holds": [{"id": "x"}]}',
        json.dumps({"holds": [_row("nope", "2026-11-04T20:00")]}),
        '{"holds": [1]}',
    ],
)
def test_corrupt_file_fails_closed_and_logs(
    data_file: Path, caplog: pytest.LogCaptureFixture, content: str
) -> None:
    data_file.parent.mkdir(parents=True)
    data_file.write_text(content, encoding="utf-8")
    with caplog.at_level(logging.ERROR, logger="holds"):
        assert holds.active(WED) is None
        assert holds.covers("g", WED) is False
        assert holds.next_change(WED) is None
    assert "holds" in caplog.text
    with pytest.raises(holds.HoldsError, match="unreadable"):
        holds.add(WED, WED_END, REASON, now=NOW)
    assert data_file.read_text(encoding="utf-8") == content


def test_unreadable_file_fails_closed(data_file: Path) -> None:
    data_file.mkdir(parents=True)  # a directory where the file should be
    assert holds.active(WED) is None


def test_missing_file_is_empty_without_error(caplog: pytest.LogCaptureFixture) -> None:
    assert holds.active(WED) is None
    assert caplog.text == ""


def test_hand_edited_overlap_picks_earliest_start(data_file: Path) -> None:
    _seed(
        data_file,
        [
            _row("2026-11-04T18:00", "2026-11-04T21:00", "b"),
            _row("2026-11-04T17:00", "2026-11-04T19:00", "a"),
        ],
    )
    found = holds.active(datetime(2026, 11, 4, 18, 30))
    assert found is not None
    assert found.id == "a"


def test_make_id_suffixes_on_collision() -> None:
    from holds._rules import make_id

    taken = holds.Hold("20261104T1700-x", WED, WED_END, REASON, NOW)
    twice = holds.Hold("20261104T1700-x-2", WED, WED_END, REASON, NOW)
    assert make_id([taken, twice], WED, "x") == "20261104T1700-x-3"
