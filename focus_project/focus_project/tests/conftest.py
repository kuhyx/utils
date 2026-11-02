# Copyright (c) 2026 Krzysztof Rudnicki
"""Redirect the data directory away from the real one, for every test.

Every path resolves through :func:`focus_project._paths.data_dir`, which
honours ``FOCUS_PROJECT_DATA``, so one env var moves all of them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _redirect_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point the data directory at ``tmp_path`` before any test runs."""
    monkeypatch.setenv("FOCUS_PROJECT_DATA", str(tmp_path / "data"))


@pytest.fixture
def data(tmp_path: Path) -> Path:
    """The redirected data directory (may not exist yet)."""
    return tmp_path / "data"
