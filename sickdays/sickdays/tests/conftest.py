# Copyright (c) 2026 Krzysztof Rudnicki
"""Redirect every on-disk path, and the free-day pool, away from real state.

Every writer resolves its paths through :func:`sickdays._paths.resolve_paths`,
so redirecting that one function in each module that imports it moves all of
them, including any file added later.

The cross-pool check would otherwise import the real freedays and read the
real ``~/.local/share/freedays`` pool, so it is stubbed to "nothing is free"
for every test; tests of the check itself pass their own predicate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from sickdays._paths import Paths

if TYPE_CHECKING:
    from datetime import date
    from pathlib import Path

_MODULES = ("sickdays._api", "sickdays._audit", "sickdays._conflict", "sickdays._sync")


def _never_free(_day: date) -> bool:
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


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    """The redirected state directory, for tests that assert on files."""
    return tmp_path / "state"
