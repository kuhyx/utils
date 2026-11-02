# Copyright (c) 2026 Krzysztof Rudnicki
"""Redirect the data directory away from the real one, for every test.

Every path resolves through :func:`focus_project._paths.data_dir`, which
honours ``FOCUS_PROJECT_DATA``, so one env var moves all of them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from focus_project import _clock

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _redirect_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point the data directory at ``tmp_path`` before any test runs."""
    monkeypatch.setenv("FOCUS_PROJECT_DATA", str(tmp_path / "data"))
    # Read-only evidence files and the signing key: never the real ones.
    monkeypatch.setenv("FOCUS_PROJECT_LEETCODE_LEDGER", str(tmp_path / "lc.json"))
    monkeypatch.setenv("KUHYTRACK_ENV", str(tmp_path / "no-kuhytrack-env"))
    monkeypatch.setenv("FOCUS_PROJECT_KEY", str(tmp_path / "hmac.key"))


@pytest.fixture(autouse=True)
def _far_future_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin "now" to 2030 so fixture days of 2026 are past, never in the future.

    Tests about the clock itself set ``_clock.now`` explicitly.
    """
    monkeypatch.setattr(_clock, "now", lambda: 1_893_456_000.0)


@pytest.fixture
def data(tmp_path: Path) -> Path:
    """The redirected data directory (may not exist yet)."""
    return tmp_path / "data"
