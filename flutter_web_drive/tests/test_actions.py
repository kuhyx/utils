"""Verbs that act on one attached page."""

from __future__ import annotations

import pytest

from flutter_web_drive import actions, cdp
from flutter_web_drive.errors import EXIT_USAGE, DriveError
from flutter_web_drive.tests.fakes import FakeClock, FakePage, node

TABS = [
    node(4, "Library\nTab 1 of 4", rect=(0, 8, 80, 67), flags=("current",)),
    node(5, "Browse\nTab 2 of 4", rect=(0, 75, 80, 67)),
    node(12, "Library", role="", tag="h2", tappable=False),
]


def _sess(page: FakePage) -> tuple[cdp.Session, FakeClock]:
    return cdp.Session(page.ws()), FakeClock()


def test_ensure_semantics_returns_nodes_once_they_appear() -> None:
    page = FakePage(nodes=TABS, semantics_on=False)
    sess, clock = _sess(page)
    clock_sleep = clock.sleep

    def flip(seconds: float) -> None:
        clock_sleep(seconds)
        page.semantics_on = True

    clock.sleep = flip  # type: ignore[method-assign]
    assert [n.id for n in actions.ensure_semantics(sess, clock)] == [4, 5, 12]


def test_ensure_semantics_times_out() -> None:
    sess, clock = _sess(FakePage(semantics_on=False))
    with pytest.raises(DriveError, match="no Flutter semantics"):
        actions.ensure_semantics(sess, clock, timeout=1)


def test_tap_clicks_center_of_best_match_and_reports_ambiguity() -> None:
    page = FakePage(nodes=TABS)
    sess, clock = _sess(page)
    out = actions.tap(sess, clock, "Library")
    assert page.clicks == [(40.0, 41.5)]
    assert out.startswith("tapped #4 button")
    assert "(2 matches; took the first)" in out
    assert "matches" not in actions.tap(sess, clock, "browse", contains=True)


def test_tap_unknown_label_lists_what_is_tappable() -> None:
    sess, clock = _sess(FakePage(nodes=TABS))
    with pytest.raises(
        DriveError, match=r'no node labelled "Sources".*"Browse \| Tab 2 of 4"'
    ):
        actions.tap(sess, clock, "Sources")


def test_tap_refuses_offscreen_nodes() -> None:
    page = FakePage(nodes=[node(7, "Far", rect=(0, 2000, 10, 10))])
    sess, clock = _sess(page)
    with pytest.raises(DriveError, match="off-screen"):
        actions.tap(sess, clock, "Far")
    assert page.clicks == []


def test_tap_xy_sends_move_press_release() -> None:
    page = FakePage()
    sess = cdp.Session(ws := page.ws())
    assert actions.tap_xy(sess, 3, 4) == "tapped (3, 4)"
    kinds = [
        m["params"]["type"]
        for m in ws.sent
        if m["method"] == "Input.dispatchMouseEvent"
    ]
    assert kinds == ["mouseMoved", "mousePressed", "mouseReleased"]


def test_insert_text_needs_a_focused_field() -> None:
    page = FakePage(focused=False)
    sess = cdp.Session(ws := page.ws())
    with pytest.raises(DriveError, match="tap the field first"):
        actions.insert_text(sess, "x")
    page.focused = True
    assert actions.insert_text(sess, "secret") == "inserted 6 characters"
    assert ws.sent[-1] == {
        "id": 3,
        "method": "Input.insertText",
        "params": {"text": "secret"},
    }


def test_press_key_sends_down_and_up_with_text_for_enter() -> None:
    page = FakePage()
    sess = cdp.Session(ws := page.ws())
    assert actions.press_key(sess, "Enter") == "pressed Enter"
    down, up = ws.sent
    assert down["params"]["type"] == "keyDown"
    assert down["params"]["text"] == "\r"
    assert up["params"]["type"] == "keyUp"
    actions.press_key(sess, "Escape")
    assert "text" not in ws.sent[2]["params"]


def test_press_key_rejects_unknown_names() -> None:
    sess = cdp.Session(FakePage().ws())
    with pytest.raises(DriveError) as err:
        actions.press_key(sess, "Hyper")
    assert err.value.code == EXIT_USAGE


def test_scroll_defaults_to_viewport_center() -> None:
    page = FakePage(viewport=(1000, 800))
    sess = cdp.Session(ws := page.ws())
    assert actions.scroll(sess, 0, 300) == "scrolled (0, 300) at (500, 400)"
    wheel = ws.sent[-1]["params"]
    assert (wheel["type"], wheel["x"], wheel["deltaY"]) == ("mouseWheel", 500, 300)
    assert actions.scroll(sess, 1, 2, at=(5, 6)) == "scrolled (1, 2) at (5, 6)"


def test_wait_for_present_and_gone() -> None:
    page = FakePage(nodes=[])
    sess, clock = _sess(page)
    sleep = clock.sleep

    def appear(seconds: float) -> None:
        sleep(seconds)
        page.nodes = TABS

    clock.sleep = appear  # type: ignore[method-assign]
    found = actions.wait_for(sess, clock, "Browse", timeout=5, on_timeout=lambda: "x")
    assert found.startswith("found #5")
    gone = actions.wait_for(
        sess, clock, "Sources", timeout=5, gone=True, on_timeout=lambda: "x"
    )
    assert gone == 'gone: "Sources"'


def test_wait_for_flag_requires_the_flag() -> None:
    sess, clock = _sess(FakePage(nodes=TABS))
    found = actions.wait_for(
        sess, clock, "Library", timeout=1, flag="current", on_timeout=lambda: "x"
    )
    assert found.startswith("found #4")
    with pytest.raises(DriveError, match=r'"Browse" \[current\] not present'):
        actions.wait_for(
            sess, clock, "Browse", timeout=1, flag="current", on_timeout=lambda: "x"
        )
    gone = actions.wait_for(
        sess,
        clock,
        "Browse",
        timeout=1,
        flag="current",
        gone=True,
        on_timeout=lambda: "x",
    )
    assert gone == 'gone: "Browse" [current]'
