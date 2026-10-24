"""Verbs that report from one attached page: shots, eval, console, rows."""

from __future__ import annotations

from pathlib import Path

import pytest

from flutter_web_drive import actions, cdp
from flutter_web_drive.errors import DriveError
from flutter_web_drive.tests.fakes import FakeClock, FakePage, node

TABS = [
    node(4, "Library\nTab 1 of 4", rect=(0, 8, 80, 67), flags=("current",)),
    node(5, "Browse\nTab 2 of 4", rect=(0, 75, 80, 67)),
    node(12, "Library", role="", tag="h2", tappable=False),
]


def _sess(page: FakePage) -> tuple[cdp.Session, FakeClock]:
    return cdp.Session(page.ws()), FakeClock()


def test_wait_for_timeout_names_screenshot() -> None:
    sess, clock = _sess(FakePage(nodes=TABS))
    with pytest.raises(DriveError, match=r"present after 1s; screenshot /s\.png"):
        actions.wait_for(
            sess, clock, "Library", timeout=1, gone=True, on_timeout=lambda: "/s.png"
        )
    with pytest.raises(DriveError, match="not present"):
        actions.wait_for(sess, clock, "Nope", timeout=1, on_timeout=lambda: "/s.png")


def test_screenshot_writes_png_and_reports_stats(tmp_path: Path) -> None:
    sess = cdp.Session(FakePage().ws())
    out = tmp_path / "a" / "s.png"
    msg = actions.screenshot(sess, out, min_colours=2)
    assert out.read_bytes().startswith(b"\x89PNG")
    assert msg == f"{out} 1400x900 colours=180 stddev=9.0"


def test_screenshot_flags_blank_frames(tmp_path: Path) -> None:
    page = FakePage(stats={"w": 10, "h": 10, "colours": 1, "stddev": 0.0})
    with pytest.raises(DriveError, match="looks blank"):
        actions.screenshot(cdp.Session(page.ws()), tmp_path / "b.png", min_colours=2)


def test_evaluate_serialises_value() -> None:
    sess = cdp.Session(FakePage(evals={"x": {"a": [1]}}).ws())
    assert actions.evaluate(sess, "x") == '{"a": [1]}'


EVENTS = [
    {
        "method": "Runtime.consoleAPICalled",
        "params": {"type": "log", "args": [{"value": "hi"}]},
    },
    {
        "method": "Runtime.consoleAPICalled",
        "params": {"type": "error", "args": [{"value": "bad"}, {"description": "Obj"}]},
    },
    {
        "method": "Runtime.consoleAPICalled",
        "params": {"type": "warning", "args": [{"value": "meh"}]},
    },
    {
        "method": "Runtime.exceptionThrown",
        "params": {
            "exceptionDetails": {
                "text": "Uncaught",
                "exception": {"description": "Error: x\n  at y"},
            }
        },
    },
    {
        "method": "Runtime.exceptionThrown",
        "params": {"exceptionDetails": {"text": "Uncaught"}},
    },
    {
        "method": "Log.entryAdded",
        "params": {"entry": {"level": "error", "text": "404"}},
    },
    {
        "method": "Log.entryAdded",
        "params": {"entry": {"level": "warning", "text": "webgl"}},
    },
    {
        "method": "Log.entryAdded",
        "params": {"entry": {"level": "info", "text": "fine"}},
    },
    {"method": "Page.loadEventFired", "params": {}},
]


def test_console_lists_errors_and_optionally_warnings() -> None:
    page = FakePage()
    out, errors = actions.console(cdp.Session(page.ws(EVENTS)))
    assert errors == 4
    assert out.splitlines() == [
        "error: bad Obj",
        "error: Uncaught Error: x",
        "error: Uncaught",
        "error: 404",
    ]
    out, _ = actions.console(cdp.Session(page.ws(EVENTS)), limit=2, warnings=True)
    assert out.splitlines() == ["error: 404", "warning: webgl"]
    assert actions.console(cdp.Session(page.ws([]))) == ("no console errors", 0)


def test_wait_for_row_scopes_the_search() -> None:
    page = FakePage(
        nodes=[
            node(1, "Chapter 2", rect=(0, 100, 1000, 60)),
            node(2, "Mark unread", rect=(900, 110, 40, 40)),
            node(3, "Chapter 1", rect=(0, 160, 1000, 60)),
            node(4, "Mark read", rect=(900, 170, 40, 40)),
        ]
    )
    sess, clock = _sess(page)
    hit = actions.wait_for(
        sess, clock, "Mark unread", row="Chapter 2", timeout=1, on_timeout=lambda: "x"
    )
    assert hit.startswith("found #2")
    with pytest.raises(
        DriveError, match=r'"Mark unread" in row "Chapter 1" not present'
    ):
        actions.wait_for(
            sess,
            clock,
            "Mark unread",
            row="Chapter 1",
            timeout=1,
            on_timeout=lambda: "x",
        )
