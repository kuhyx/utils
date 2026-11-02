# Copyright (c) 2026 Krzysztof Rudnicki
"""The browser adapter: window/URL time on a project's sites, AFK-trimmed."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from urllib.error import URLError

import pytest

from focus_project import sources
from focus_project._model import Project
from focus_project.sources import browser

DAY = date(2026, 11, 2)
LO, HI = sources.day_bounds(DAY)
CFG = browser.Config("http://tracker.test", "tok")


def _project(*patterns: str) -> Project:
    return Project(
        id="p",
        name="P",
        start=DAY,
        end=DAY,
        replaces=("leetcode",),
        daily_minutes=120,
        unlock_minutes=30,
        site_patterns=patterns,
    )


def _iso(offset: float) -> str:
    stamp = datetime.fromtimestamp(LO + offset, UTC)
    return stamp.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _ev(offset: float, dur: float, **data: str) -> dict[str, Any]:
    return {"timestamp": _iso(offset), "duration": dur, "data": data}


def _bucket(bid: str, kind: str, host: str) -> dict[str, Any]:
    return {"id": bid, "type": kind, "hostname": host}


def _fake_tracker(
    monkeypatch: pytest.MonkeyPatch,
    buckets: list[dict[str, Any]],
    events: dict[str, list[dict[str, Any]]],
) -> list[tuple[str, dict[str, str] | None]]:
    calls: list[tuple[str, dict[str, str] | None]] = []

    def fake(
        _cfg: browser.Config, path: str, params: dict[str, str] | None = None
    ) -> Any:  # noqa: ANN401
        calls.append((path, params))
        if path == "/api/0/buckets":
            return {b["id"]: b for b in buckets}
        bid = path.split("/")[4]
        return events.get(bid, [])

    monkeypatch.setattr(browser, "_get_json", fake)
    monkeypatch.setattr(browser, "_config", lambda: CFG)
    return calls


WIN = _bucket("win_pc", "currentwindow", "pc")
AFK = _bucket("afk_pc", "afkstatus", "pc")
ACTIVE_ALL = [_ev(0, 86000, status="not-afk")]


def test_title_stem_in_browser_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_tracker(
        monkeypatch,
        [WIN, AFK],
        {
            "win_pc": [
                _ev(100, 600, app="Helium", title="Two Sum - LeetCode - Helium")
            ],
            "afk_pc": ACTIVE_ALL,
        },
    )
    assert browser.intervals(DAY, _project("leetcode.com")) == [(LO + 100, LO + 700)]


def test_stem_ignored_outside_browsers(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_tracker(
        monkeypatch,
        [WIN, AFK],
        {
            "win_pc": [_ev(0, 600, app="Terminator", title="notes on leetcode")],
            "afk_pc": ACTIVE_ALL,
        },
    )
    assert browser.intervals(DAY, _project("leetcode.com")) == []


def test_full_pattern_matches_any_app_and_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_tracker(
        monkeypatch,
        [WIN],
        {
            "win_pc": [
                _ev(0, 60, app="x", title="t", url="https://HackerRank.com/a"),
                _ev(100, 60, app="mpv", title="www.hackerrank.com talk"),
            ]
        },
    )
    got = browser.intervals(DAY, _project("hackerrank.com"))
    assert got == [(LO, LO + 60), (LO + 100, LO + 160)]


def test_afk_time_is_cut(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_tracker(
        monkeypatch,
        [WIN, AFK],
        {
            "win_pc": [_ev(0, 1000, app="Helium", title="LeetCode")],
            "afk_pc": [
                _ev(100, 200, status="not-afk"),
                _ev(500, 100, status="not-afk"),
            ],
        },
    )
    assert browser.intervals(DAY, _project("leetcode.com")) == [
        (LO + 100, LO + 300),
        (LO + 500, LO + 600),
    ]


def test_afk_bucket_without_events_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_tracker(
        monkeypatch,
        [WIN, AFK],
        {"win_pc": [_ev(0, 1000, app="Helium", title="LeetCode")], "afk_pc": []},
    )
    assert browser.intervals(DAY, _project("leetcode.com")) == []


def test_phone_bucket_has_no_afk_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    phone = _bucket("win_ph", "currentwindow", "pixel6a")
    _fake_tracker(
        monkeypatch,
        [phone],
        {"win_ph": [_ev(10, 90, app="Chrome", title="HackerRank")]},
    )
    assert browser.intervals(DAY, _project("hackerrank.com")) == [(LO + 10, LO + 100)]


def test_hosts_do_not_borrow_each_others_afk(monkeypatch: pytest.MonkeyPatch) -> None:
    other = _bucket("afk_other", "afkstatus", "other")
    _fake_tracker(
        monkeypatch,
        [WIN, AFK, other],
        {
            "win_pc": [_ev(0, 100, app="Helium", title="LeetCode")],
            "afk_pc": ACTIVE_ALL,
            "afk_other": [],
        },
    )
    assert browser.intervals(DAY, _project("leetcode.com")) == [(LO, LO + 100)]


def test_no_patterns_no_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake_tracker(monkeypatch, [WIN], {})
    assert browser.intervals(DAY, _project()) == []
    assert calls == []


def test_short_stem_needs_the_full_pattern(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_tracker(
        monkeypatch,
        [WIN],
        {"win_pc": [_ev(0, 60, app="Helium", title="go to the shop")]},
    )
    assert browser.intervals(DAY, _project("go.dev")) == []


def test_query_is_bounded_to_the_day(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake_tracker(monkeypatch, [WIN], {})
    browser.intervals(DAY, _project("leetcode.com"))
    params = next(p for path, p in calls if path.endswith("/events"))
    assert params is not None
    assert params["start"] < params["end"]


def test_no_config_is_inactive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(browser, "_config", lambda: None)
    assert browser.intervals(DAY, _project("leetcode.com")) == []


def test_unreachable_tracker_raises_for_the_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reason = "down"

    def boom(*_a: object, **_k: object) -> None:
        raise URLError(reason)

    monkeypatch.setattr(browser, "_get_json", boom)
    monkeypatch.setattr(browser, "_config", lambda: CFG)
    project = _project("leetcode.com")
    with pytest.raises(URLError):
        browser.intervals(DAY, project)
    assert sources.collect_by_source(DAY, project)["browser"] == []
