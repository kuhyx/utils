"""Redirect every on-disk path away from real user state, for every test.

This is one ``monkeypatch`` of one function, and that is the whole point.
An earlier version patched five separate module attributes by name, which
meant a module that started importing a sixth path constant would keep
writing to ``~/.local/share/freedays`` while the suite still looked green --
the exact way a test run in this fleet once wrote 27 fake entries into a
live log.

Because every writer resolves its paths through
:func:`freedays._paths.resolve_paths`, redirecting that one function moves
all of them, including any file added later.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from freedays._paths import Paths

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _redirect_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point every default path at ``tmp_path`` before any test runs."""
    state = tmp_path / "state"
    state.mkdir()
    redirected = Paths.under(state)

    def _resolve(paths: Paths | None) -> Paths:
        return paths if paths is not None else redirected

    for module in ("freedays._api", "freedays._audit", "freedays._sync"):
        monkeypatch.setattr(f"{module}.resolve_paths", _resolve)


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    """The redirected state directory, for tests that assert on files."""
    return tmp_path / "state"
