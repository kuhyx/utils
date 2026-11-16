# Copyright (c) 2026 Krzysztof Rudnicki
"""Finding the game's window by pid: xdotool is faked, the clock is stepped by hand."""

from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from game_recording import window

GEOMETRY = {
    "1": "WINDOW=1\nX=0\nY=0\nWIDTH=1280\nHEIGHT=800\nSCREEN=0\n",
    "2": "WIDTH=32\nHEIGHT=32\n",
    "3": "WIDTH=1920\nHEIGHT=1080\n",
    "4": "WIDTH=wide\nHEIGHT=1080\n",
}
A = window.Window(1, 1280, 800)
B = window.Window(1, 1920, 1080)


def fake_xdotool(*args: str) -> str:
    if args[0] == "search":
        return "1 2 3 4 5\n"
    return GEOMETRY.get(args[-1], "")


def test_xdotool_output_is_returned_on_success_and_empty_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []
    codes = iter([0, 1])

    def fake_run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, next(codes), stdout="out")

    monkeypatch.setattr("game_recording.window.subprocess", SimpleNamespace(run=fake_run))
    assert window._run("search", "--pid", "7") == "out"
    assert Path(calls[0][0]).name == "xdotool"
    assert calls[0][1:] == ["search", "--pid", "7"]
    assert window._run("search") == ""


def test_the_biggest_real_window_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(window, "_run", fake_xdotool)
    assert window.largest(7) == window.Window(3, 1920, 1080)


def test_helper_and_unreadable_windows_are_not_the_game(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(window, "_run", lambda *_args: "")
    assert window.largest(7) is None


def test_a_window_with_odd_geometry_text_is_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(window, "_run", fake_xdotool)
    assert window._geometry("4") is None
    assert window._geometry("5") is None


def wait(
    monkeypatch: pytest.MonkeyPatch, sizes: list[window.Window | None], alive: list[bool] | None = None
) -> window.Window | None:
    clock = iter(range(1000))
    sizes_iter = iter(sizes)
    sleeps: list[float] = []
    flags = iter(alive or [True] * len(sizes))
    monkeypatch.setattr(window, "largest", lambda _pid: next(sizes_iter))
    monkeypatch.setattr(
        "game_recording.window.time", SimpleNamespace(monotonic=lambda: next(clock), sleep=sleeps.append)
    )
    result = window.wait_stable(7, 50.0, lambda: next(flags, False))
    assert len(sleeps) <= len(sizes)
    return result


@pytest.mark.parametrize(
    ("sizes", "expected"),
    [
        ([A, A, A], A),
        ([A, A, B, B, B], B),
        ([None, None, A, A, A], A),
    ],
    ids=["holds-still", "resize-restarts-count", "no-window-yet"],
)
def test_wait_stable_returns_the_settled_window(
    monkeypatch: pytest.MonkeyPatch, sizes: list[window.Window | None], expected: window.Window
) -> None:
    assert wait(monkeypatch, sizes) == expected


def test_a_game_that_exits_ends_the_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    assert wait(monkeypatch, [A, A, A], alive=[True, False]) is None


def test_the_deadline_ends_the_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = iter([0.0, 1.0, 100.0])
    monkeypatch.setattr(window, "largest", lambda _pid: None)
    monkeypatch.setattr(
        "game_recording.window.time", SimpleNamespace(monotonic=lambda: next(clock), sleep=lambda _s: None)
    )
    assert window.wait_stable(7, 5.0, lambda: True) is None
