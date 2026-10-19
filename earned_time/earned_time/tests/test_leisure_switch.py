# Copyright (c) 2026 Krzysztof Rudnicki
"""The leisure switch file (0.15.0): ``/etc/leisure-watch/leisure_from``."""

from __future__ import annotations

from datetime import date, timedelta
import inspect
import os
from pathlib import Path

import pytest

from earned_time import (
    LEISURE_FROM,
    LEISURE_FROM_PATH,
    TUTOR_EARNERS,
    UNIFIED_FROM,
    base_for,
    gaming_base_minutes_for,
    gaming_ceiling_minutes_for,
    leisure_active,
    leisure_from,
    resolve,
)

DAY = date(2026, 10, 20)
FULL = {"workout": 1, "leetcode": 1, "reading": 1, "tutor": 60}
NONE = dict.fromkeys(FULL, 0)


def _switch(tmp_path: Path, content: bytes) -> Path:
    path = tmp_path / "leisure_from"
    path.write_bytes(content)
    return path


@pytest.fixture
def live(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The module's switch path, holding ``DAY`` (go-live wrote it)."""
    path = _switch(tmp_path, b"2026-10-20\n")
    monkeypatch.setattr("earned_time._leisure.LEISURE_FROM_PATH", path)
    return path


def test_default_path_is_the_etc_switch_file() -> None:
    assert Path("/etc/leisure-watch/leisure_from") == LEISURE_FROM_PATH
    for func in (leisure_from, leisure_active):
        assert inspect.signature(func).parameters["path"].default == LEISURE_FROM_PATH


def test_missing_file_is_parked(tmp_path: Path) -> None:
    assert leisure_from(tmp_path / "absent") == LEISURE_FROM
    assert not leisure_active(DAY, tmp_path / "absent")


@pytest.mark.parametrize("content", [b"2026-10-20", b"2026-10-20\n"])
def test_valid_date_is_read(tmp_path: Path, content: bytes) -> None:
    assert leisure_from(_switch(tmp_path, content)) == DAY


def test_file_date_is_the_first_leisure_day(tmp_path: Path) -> None:
    path = _switch(tmp_path, b"2026-10-21\n")  # go-live on the 20th: tomorrow
    assert not leisure_active(DAY, path)
    assert leisure_active(DAY + timedelta(days=1), path)
    assert leisure_active(DAY + timedelta(days=2), path)
    assert leisure_active(DAY, _switch(tmp_path, b"2026-10-20\n"))  # today


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"garbage\n",
        b"2026-13-01\n",
        b"2026-02-30\n",
        b"20261020\n",
        b"2026-W43-2\n",
        b" 2026-10-20\n",
        b"2026-10-20\n\n",
        b"2026-10-20 \n",
        b"2026-10-20\r\n",
        b"2026-10-\xef\xbc\x920\n",  # fullwidth digit two
        b"\xff\xfe2026-10-20",
    ],
)
def test_garbage_is_parked(tmp_path: Path, content: bytes) -> None:
    assert leisure_from(_switch(tmp_path, content)) == LEISURE_FROM


def test_oversize_file_is_parked(tmp_path: Path) -> None:
    assert leisure_from(_switch(tmp_path, b"2026-10-20\n" + b"\n" * 54)) == LEISURE_FROM
    assert leisure_from(_switch(tmp_path, b"2026-10-20" + b" " * 54)) == LEISURE_FROM


def test_fifo_is_parked_without_blocking(tmp_path: Path) -> None:
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    assert leisure_from(fifo) == LEISURE_FROM


def test_directory_is_parked(tmp_path: Path) -> None:
    assert leisure_from(tmp_path) == LEISURE_FROM


def test_symlink_is_parked_even_to_a_valid_file(tmp_path: Path) -> None:
    target = _switch(tmp_path, b"2026-10-20\n")
    link = tmp_path / "link"
    link.symlink_to(target)
    assert leisure_from(target) == DAY
    assert leisure_from(link) == LEISURE_FROM


def test_unreadable_file_is_parked(tmp_path: Path) -> None:
    path = _switch(tmp_path, b"2026-10-20\n")
    path.chmod(0)
    try:
        if os.access(path, os.R_OK):  # pragma: no cover - running as root
            pytest.skip("root reads a 0000 file")
        assert leisure_from(path) == LEISURE_FROM
    finally:
        path.chmod(0o644)


def test_file_appearing_mid_run_is_seen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "leisure_from"
    monkeypatch.setattr("earned_time._leisure.LEISURE_FROM_PATH", path)
    assert gaming_base_minutes_for(DAY) == 300
    path.write_bytes(b"2026-10-20\n")
    assert gaming_base_minutes_for(DAY) == 420
    path.unlink()
    assert gaming_base_minutes_for(DAY) == 300


@pytest.mark.usefixtures("live")
def test_base_and_ceiling_follow_the_file() -> None:
    eve = DAY - timedelta(days=1)
    assert gaming_base_minutes_for(eve) == 300
    assert gaming_ceiling_minutes_for(eve) == 480
    assert gaming_base_minutes_for(DAY) == 420
    assert gaming_ceiling_minutes_for(DAY) == 600


@pytest.mark.usefixtures("live")
def test_resolve_and_base_for_follow_the_file() -> None:
    eve = DAY - timedelta(days=1)
    assert base_for(eve).gaming_minutes == 180
    assert base_for(DAY).gaming_minutes == 300
    assert resolve(NONE, eve, TUTOR_EARNERS).gaming_minutes == 180
    assert resolve(FULL, eve, TUTOR_EARNERS).gaming_minutes == 480
    assert resolve(NONE, DAY, TUTOR_EARNERS).gaming_minutes == 300
    assert resolve(FULL, DAY, TUTOR_EARNERS).gaming_minutes == 600


def test_leisure_flag_still_forces_past_a_later_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _switch(tmp_path, b"2027-06-01\n")
    monkeypatch.setattr("earned_time._leisure.LEISURE_FROM_PATH", path)
    assert base_for(UNIFIED_FROM, leisure=True).gaming_minutes == 300
    assert (
        resolve(NONE, UNIFIED_FROM, TUTOR_EARNERS, leisure=True).gaming_minutes == 300
    )
    assert (
        resolve(FULL, UNIFIED_FROM, TUTOR_EARNERS, leisure=True).gaming_minutes == 600
    )
    assert resolve(FULL, date(2027, 1, 2), TUTOR_EARNERS).gaming_minutes == 480
