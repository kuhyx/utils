# Copyright (c) 2026 Krzysztof Rudnicki
"""Tests for the top-right status strip shown while a gate stands down."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from gatelock import corner_strip
from gatelock._config import LockConfig
from gatelock._outputs import Output, OutputRect, OutputScan
from gatelock.corner_strip import (
    CornerStrip,
    StripContent,
    build_corner_strip,
    corner_geometry,
    corner_rect,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    import pytest

_LEFT = Output("DP-0", connected=True, rect=OutputRect(0, 0, 3840, 2160))
_RIGHT = Output(
    "HDMI-0", connected=True, rect=OutputRect(3840, 0, 2560, 1440), primary=True
)
_DARK = Output("DP-1", connected=False, rect=None)


def test_corner_rect_prefers_the_primary_output() -> None:
    scan = OutputScan((_LEFT, _RIGHT), source="randr", ok=True)
    assert corner_rect(scan) == _RIGHT.rect


def test_corner_rect_falls_back_to_the_first_live_output() -> None:
    left = Output("DP-0", connected=True, rect=OutputRect(0, 0, 100, 100))
    scan = OutputScan((_DARK, left), source="randr", ok=True)
    assert corner_rect(scan) == left.rect


def test_corner_rect_is_none_when_nothing_is_live() -> None:
    assert corner_rect(OutputScan((_DARK,), source="randr", ok=True)) is None


def test_geometry_hugs_the_top_right_corner_of_the_rect() -> None:
    rect = OutputRect(3840, 0, 2560, 1440)
    assert corner_geometry(rect, width=400, height=120, inset=16) == ("400x120+5984+16")


def _after_into(jobs: list[Callable[[], None]]) -> Callable[..., str]:
    """A ``window.after`` stand-in that queues the callback instead of timing it."""

    def after(_ms: int, fn: Callable[[], None]) -> str:
        jobs.append(fn)
        return f"job{len(jobs)}"

    return after


def _strip() -> tuple[CornerStrip, MagicMock, MagicMock, list[MagicMock]]:
    window, title = MagicMock(), MagicMock()
    lines = [MagicMock(), MagicMock()]
    return CornerStrip(window, title, lines, tick_ms=50), window, title, lines


def test_show_writes_title_and_lines_and_relifts() -> None:
    strip, window, title, lines = _strip()
    strip.show(StripContent("Morning session", ("Next: shower", "Locks at 09:13")))
    title.configure.assert_called_with(text="Morning session")
    lines[0].configure.assert_called_with(text="Next: shower")
    lines[1].configure.assert_called_with(text="Locks at 09:13")
    window.lift.assert_called()


def test_show_blanks_lines_the_content_does_not_fill() -> None:
    strip, _window, _title, lines = _strip()
    strip.show(StripContent("t", ("only one",)))
    lines[1].configure.assert_called_with(text="")


def test_schedule_ticks_until_the_supply_says_none_then_closes() -> None:
    strip, window, _title, _lines = _strip()
    jobs: list[Callable[[], None]] = []
    window.after.side_effect = _after_into(jobs)
    supplies = iter([StripContent("a", ()), None])
    closed: list[bool] = []
    strip.schedule(lambda: next(supplies), on_close=lambda: closed.append(True))
    jobs.pop(0)()  # first tick: content -> shown, rescheduled
    assert jobs, "the tick must reschedule itself while there is content"
    jobs.pop(0)()  # second tick: None -> closed, not rescheduled
    assert not jobs
    assert closed == [True]
    window.destroy.assert_called_once()


def test_destroy_is_idempotent_and_cancels_the_tick() -> None:
    strip, window, _title, _lines = _strip()
    window.after.return_value = "job1"
    strip.schedule(lambda: StripContent("a", ()), on_close=lambda: None)
    strip.destroy()
    strip.destroy()
    window.after_cancel.assert_called_once_with("job1")
    window.destroy.assert_called_once()


def test_a_tcl_error_on_refresh_stops_the_strip_loudly(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import tkinter as tk

    strip, window, title, _lines = _strip()
    title.configure.side_effect = tk.TclError("gone")
    strip.show(StripContent("a", ()))
    assert "could not refresh" in caplog.text
    strip.destroy()
    window.destroy.assert_not_called()


def test_build_places_an_override_redirect_topmost_window() -> None:
    window = MagicMock()
    window.winfo_reqheight.return_value = 90
    with (
        patch.object(corner_strip.tk, "Toplevel", return_value=window),
        patch.object(corner_strip.tk, "Label", side_effect=lambda *a, **k: MagicMock()),
    ):
        strip = build_corner_strip(
            MagicMock(),
            LockConfig(),
            StripContent("Morning session", ("Next: shower",)),
            rect=OutputRect(0, 0, 1920, 1080),
            max_lines=2,
        )
    window.overrideredirect.assert_called_once_with(boolean=True)
    window.attributes.assert_called_with("-topmost", 1)
    spec = window.geometry.call_args.args[0]
    assert spec.startswith("420x90+")
    assert isinstance(strip, CornerStrip)


def test_closed_reports_destroyed_state() -> None:
    strip, _window, _title, _lines = _strip()
    assert strip.closed is False
    strip.destroy()
    assert strip.closed is True


def test_show_after_destroy_does_nothing() -> None:
    strip, window, title, _lines = _strip()
    strip.destroy()
    strip.show(StripContent("late", ()))
    title.configure.assert_not_called()
    window.lift.assert_not_called()


def test_schedule_after_destroy_does_not_tick() -> None:
    strip, window, _title, _lines = _strip()
    strip.destroy()
    strip.schedule(lambda: StripContent("a", ()), on_close=lambda: None)
    window.after.assert_not_called()


def test_a_tick_that_breaks_the_strip_does_not_reschedule() -> None:
    import tkinter as tk

    strip, window, title, _lines = _strip()
    jobs: list[Callable[[], None]] = []
    window.after.side_effect = _after_into(jobs)
    title.configure.side_effect = tk.TclError("gone")
    strip.schedule(lambda: StripContent("a", ()), on_close=lambda: None)
    jobs.pop(0)()
    assert strip.closed
    assert not jobs


def test_destroy_without_a_tick_skips_the_cancel() -> None:
    strip, window, _title, _lines = _strip()
    strip.destroy()
    window.after_cancel.assert_not_called()
    window.destroy.assert_called_once()


def test_destroy_logs_a_tcl_error_instead_of_raising(
    caplog: pytest.LogCaptureFixture,
) -> None:
    import tkinter as tk

    strip, window, _title, _lines = _strip()
    window.destroy.side_effect = tk.TclError("already gone")
    strip.destroy()
    assert "could not be destroyed" in caplog.text
    assert strip.closed


def test_build_with_zero_lines_builds_only_the_title() -> None:
    window = MagicMock()
    window.winfo_reqheight.return_value = 40
    with (
        patch.object(corner_strip.tk, "Toplevel", return_value=window),
        patch.object(corner_strip.tk, "Label", side_effect=lambda *a, **k: MagicMock()),
    ):
        strip = build_corner_strip(
            MagicMock(),
            LockConfig(),
            StripContent("Just a title", ()),
            rect=OutputRect(0, 0, 1920, 1080),
            max_lines=0,
        )
    assert isinstance(strip, CornerStrip)
    window.deiconify.assert_called_once()
