# Copyright (c) 2026 Krzysztof Rudnicki
"""gatelock.night_lockdown -- has tonight's evening lockdown already happened?"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from typing import TYPE_CHECKING

import pytest

from gatelock.night_lockdown import NIGHT_LOCKDOWN_STAMP, evening_lockdown_today

if TYPE_CHECKING:
    from pathlib import Path

NOW = datetime(2026, 10, 17, 22, 30).astimezone()


@pytest.fixture
def stamp(tmp_path: Path) -> Path:
    """Where the tests write the stamp -- never the real root-owned one."""
    return tmp_path / "locked_at_epoch"


def _write_local(stamp: Path, when: str) -> None:
    """Stamp the epoch of a LOCAL wall-clock time, as night-lockdown does."""
    epoch = int(datetime.fromisoformat(when).astimezone().timestamp())
    stamp.write_text(f"{epoch}\n")


def test_default_path_is_the_one_night_lockdown_writes() -> None:
    assert str(NIGHT_LOCKDOWN_STAMP) == "/var/lib/night-lockdown/locked_at_epoch"


def test_evening_lock_today_counts(stamp: Path) -> None:
    _write_local(stamp, "2026-10-17T18:00")
    got = evening_lockdown_today(stamp, NOW)
    assert got == datetime(2026, 10, 17, 18, 0).astimezone()


def test_morning_relock_today_does_not_count(
    stamp: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # The 04:01 re-lock is the night that started yesterday, not tonight's.
    _write_local(stamp, "2026-10-17T04:01")
    with caplog.at_level(logging.DEBUG, logger="gatelock.night_lockdown"):
        assert evening_lockdown_today(stamp, NOW) is None
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_noon_is_the_first_evening_minute(stamp: Path) -> None:
    _write_local(stamp, "2026-10-17T12:00")
    assert evening_lockdown_today(stamp, NOW) is not None


def test_just_before_noon_is_still_morning(stamp: Path) -> None:
    _write_local(stamp, "2026-10-17T11:59:59")
    assert evening_lockdown_today(stamp, NOW) is None


def test_yesterdays_evening_lock_does_not_count(stamp: Path) -> None:
    _write_local(stamp, "2026-10-16T21:00")
    assert evening_lockdown_today(stamp, NOW) is None


def test_lock_later_than_now_does_not_count(stamp: Path) -> None:
    # Clock trouble: a stamp from the future is not a lockdown that happened.
    _write_local(stamp, "2026-10-17T23:00")
    assert evening_lockdown_today(stamp, NOW) is None


def test_missing_file_is_quiet(stamp: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG, logger="gatelock.night_lockdown"):
        assert evening_lockdown_today(stamp, NOW) is None
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


@pytest.mark.parametrize("content", ["garbage", "", "  \n", "12.5", "1e9"])
def test_garbage_warns(
    stamp: Path, caplog: pytest.LogCaptureFixture, content: str
) -> None:
    stamp.write_text(content)
    with caplog.at_level(logging.WARNING, logger="gatelock.night_lockdown"):
        assert evening_lockdown_today(stamp, NOW) is None
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_absurd_epoch_warns(stamp: Path, caplog: pytest.LogCaptureFixture) -> None:
    stamp.write_text("9" * 30)
    with caplog.at_level(logging.WARNING, logger="gatelock.night_lockdown"):
        assert evening_lockdown_today(stamp, NOW) is None
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_unreadable_warns(stamp: Path, caplog: pytest.LogCaptureFixture) -> None:
    stamp.mkdir()  # reading a directory is an OSError that is not "missing"
    with caplog.at_level(logging.WARNING, logger="gatelock.night_lockdown"):
        assert evening_lockdown_today(stamp, NOW) is None
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_now_defaults_to_the_local_clock(stamp: Path) -> None:
    # A stamp a minute ago counts exactly when "a minute ago" is today, >=12:00.
    ago = datetime.now(tz=UTC).astimezone() - timedelta(minutes=1)
    stamp.write_text(str(int(ago.timestamp())))
    expected = ago.date() == (ago + timedelta(minutes=1)).date() and ago.hour >= 12
    assert (evening_lockdown_today(stamp) is not None) is expected
