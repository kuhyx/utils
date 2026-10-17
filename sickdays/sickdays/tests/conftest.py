# Copyright (c) 2026 Krzysztof Rudnicki
"""Redirect every on-disk path, and the free-day pool, away from real state.

Every writer resolves its paths through :func:`sickdays._paths.resolve_paths`,
so redirecting that one function in each module that imports it moves all of
them, including any file added later.

The GUI modules are in the list too, and their background sync is stubbed:
a test thread must never find the real crdt-sync credential.

The cross-pool check would otherwise import the real freedays and read the
real ``~/.local/share/freedays`` pool, so it is stubbed to "nothing is free"
for every test; tests of the check itself pass their own predicate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from sickdays._paths import Paths

if TYPE_CHECKING:
    from collections.abc import Iterator
    from datetime import date
    from pathlib import Path
    import tkinter as tk

_MODULES = (
    "sickdays._api",
    "sickdays._audit",
    "sickdays._conflict",
    "sickdays._keep_api",
    "sickdays._sync",
    "sickdays.gui._panel",
    "sickdays.gui._window",
)


def _never_free(_day: date) -> bool:
    return False


def _no_sync(*, paths: Paths | None = None) -> bool:
    """The GUI's background sync, stubbed: no test may reach Firebase."""
    del paths
    return False


@pytest.fixture(autouse=True)
def _redirect_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point every default path at ``tmp_path`` before any test runs."""
    state = tmp_path / "state"
    state.mkdir()
    redirected = Paths.under(state)

    def _resolve(paths: Paths | None) -> Paths:
        return paths if paths is not None else redirected

    for module in _MODULES:
        monkeypatch.setattr(f"{module}.resolve_paths", _resolve)
    monkeypatch.setattr("sickdays._api.free_day_predicate", lambda: _never_free)
    monkeypatch.setattr("sickdays.gui._text.free_day_predicate", lambda: _never_free)
    monkeypatch.setattr("sickdays.gui._panel.sync_quietly", _no_sync)


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    """The redirected state directory, for tests that assert on files."""
    return tmp_path / "state"


@pytest.fixture
def tk_root() -> Iterator[tk.Tk]:
    """A real, never-mapped Tk root; skips when there is no X display.

    Real Tk rather than a fake: option names and Checkbutton/variable wiring
    are Tk's own behaviour. CI runs the suite under ``xvfb-run``.
    """
    import tkinter as tk

    try:
        root = tk.Tk(className="sickdays-test")
    except tk.TclError as exc:
        pytest.skip(f"no X display ({exc}); run the suite under xvfb-run")
    root.withdraw()
    yield root
    root.destroy()
