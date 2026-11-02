"""The root password is random, private and created exactly once."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from sql_drills import _paths, _secret

if TYPE_CHECKING:
    from pathlib import Path

    from _typeshed import StrPath
    import pytest


def test_created_once_random_and_private() -> None:
    first = _secret.root_password()
    assert len(first) >= 24
    assert _secret.root_password() == first
    path = _paths.config_dir() / "root_password"
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert [p.name for p in path.parent.iterdir()] == ["root_password"]


def test_different_homes_get_different_passwords(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    one = _secret.root_password()
    monkeypatch.setenv("SQL_DRILLS_CONFIG", str(tmp_path / "other"))
    assert _secret.root_password() != one


def test_losing_the_race_reads_the_winners_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _paths.config_dir() / "root_password"
    real_link = os.link

    def winner_first(src: StrPath, dst: StrPath) -> None:
        path.write_text("winner\n", encoding="utf-8")
        real_link(src, dst)

    monkeypatch.setattr(os, "link", winner_first)
    assert _secret.root_password() == "winner"
    assert [p.name for p in path.parent.iterdir()] == ["root_password"]
