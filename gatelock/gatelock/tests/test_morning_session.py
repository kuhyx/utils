# Copyright (c) 2026 Krzysztof Rudnicki
"""gatelock.morning_session -- the carrot file, read and never re-derived."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from gatelock import morning_session
from gatelock.log_integrity import compute_entry_hmac
from gatelock.morning_session import MorningSkip, morning_skip

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

NOW = datetime(2026, 9, 19, 9, 0).astimezone()


@pytest.fixture
def path(tmp_path: Path) -> Path:
    """Where the tests write the signed file -- never the real one."""
    return tmp_path / "morning_session.json"


@pytest.fixture(autouse=True)
def _signing_key(tmp_path: Path) -> Iterator[None]:
    key = tmp_path / "hmac.key"
    key.write_bytes(b"1" * 32)
    with patch("gatelock.log_integrity.DEFAULT_HMAC_KEY_FILE", key):
        yield


def _write(path: Path, entry: dict[str, object], *, sign: bool = True) -> None:
    """Write an entry; signed unless told otherwise."""
    if sign:
        entry["hmac"] = compute_entry_hmac(entry)
    path.write_text(json.dumps(entry))


def _entry(
    outcome: str = "completed",
    exempt_until: str | None = "11:00",
    date: str = "2026-09-19",
) -> dict[str, object]:
    entry: dict[str, object] = {"date": date, "outcome": outcome}
    if exempt_until is not None:
        entry["exempt_until"] = (
            datetime.fromisoformat(f"{date}T{exempt_until}").astimezone().isoformat()
        )
    return entry


def _today_entry() -> dict[str, object]:
    today = datetime.now(tz=UTC).astimezone().strftime("%Y-%m-%d")
    return _entry(date=today, exempt_until="23:59")


class TestVerdict:
    """One rule: signed, today, not yet expired."""

    def test_completed_grants_until_the_signed_instant(self, path: Path) -> None:
        _write(path, _entry())
        skip = morning_skip(path, NOW, wait=False)
        assert skip == MorningSkip("completed", NOW.replace(hour=11))
        assert str(skip) == "completed session, no lock until 11:00"

    def test_expired_and_absent_exemptions_grant_nothing(self, path: Path) -> None:
        _write(path, _entry())
        assert morning_skip(path, NOW + timedelta(hours=3), wait=False) is None
        _write(path, _entry("failed", exempt_until=None))
        assert morning_skip(path, NOW, wait=False) is None
        _write(path, {**_entry(), "exempt_until": "later"})
        assert morning_skip(path, NOW, wait=False) is None

    def test_a_naive_exempt_until_grants_nothing(self, path: Path) -> None:
        _write(path, {**_entry(), "exempt_until": "2026-09-19T11:00:00"})
        assert morning_skip(path, NOW, wait=False) is None

    def test_yesterdays_file_is_not_today(self, path: Path) -> None:
        _write(path, _entry(date="2026-09-18"))
        assert morning_skip(path, NOW, wait=False) is None

    def test_missing_unreadable_tampered_are_all_nothing(self, path: Path) -> None:
        assert morning_skip(path, NOW, wait=False) is None
        _write(path, _entry(), sign=False)
        assert morning_skip(path, NOW, wait=False) is None
        path.write_text("[1]")
        assert morning_skip(path, NOW, wait=False) is None
        path.write_text("{")
        assert morning_skip(path, NOW, wait=False) is None
        path.unlink()
        path.mkdir()
        assert morning_skip(path, NOW, wait=False) is None

    def test_default_now_is_the_wall_clock(self, path: Path) -> None:
        _write(path, _today_entry())
        assert morning_skip(path, wait=False) is not None

    def test_default_path_is_wake_alarms_state_file(self) -> None:
        assert morning_session.MORNING_SESSION_FILE.parts[-3:] == (
            "state",
            "wake_alarm",
            "morning_session.json",
        )


class TestBootRetry:
    """The arming path waits for the refresher, bounded; status never does."""

    def test_waits_inside_the_window_then_warns(
        self, path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        naps: list[float] = []
        # The window is re-checked against the real clock after each nap.
        with patch.object(morning_session, "MORNING_WINDOW", ((0, 0), (23, 59))):
            skip = morning_skip(
                path, NOW, wait=True, retry_seconds=10.0, sleep=naps.append
            )
        assert skip is None
        assert naps == [5.0, 5.0]
        assert "is wake-alarm-session.timer running" in caplog.text

    def test_a_file_landing_mid_wait_is_honoured(self, path: Path) -> None:
        def land(_seconds: float) -> None:
            _write(path, _today_entry())

        with patch.object(morning_session, "MORNING_WINDOW", ((0, 0), (23, 59))):
            skip = morning_skip(path, NOW, wait=True, retry_seconds=10.0, sleep=land)
        assert skip is not None

    def test_never_waits_outside_the_window_or_without_wait(self, path: Path) -> None:
        naps: list[float] = []
        late = NOW.replace(hour=14)
        assert (
            morning_skip(path, late, wait=True, retry_seconds=10.0, sleep=naps.append)
            is None
        )
        assert (
            morning_skip(path, NOW, wait=False, retry_seconds=10.0, sleep=naps.append)
            is None
        )
        assert naps == []

    def test_a_zero_budget_never_waits(self, path: Path) -> None:
        naps: list[float] = []
        assert (
            morning_skip(path, NOW, wait=True, retry_seconds=0.0, sleep=naps.append)
            is None
        )
        assert naps == []
