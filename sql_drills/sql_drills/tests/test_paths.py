"""Data-dir resolution is a function, so tests (and users) can redirect it."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sql_drills import _paths, data_dir

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_env_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SQL_DRILLS_DATA", str(tmp_path / "x"))
    assert data_dir() == tmp_path / "x"


def test_default_is_under_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("SQL_DRILLS_DATA")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert data_dir() == tmp_path / ".local" / "share" / "sql_drills"


def test_empty_env_falls_back(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SQL_DRILLS_DATA", "")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert data_dir().name == "sql_drills"


def test_builtin_dir_ships_fixtures() -> None:
    assert (_paths.builtin_dir() / "01_pivot_sum" / "meta.json").is_file()
