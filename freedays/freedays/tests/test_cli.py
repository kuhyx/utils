# Copyright (c) 2026 Krzysztof Rudnicki
"""The command line: the only surface that ever mentions free days."""

from __future__ import annotations

from datetime import timedelta

import pytest

from freedays._cli import main
from freedays._day import to_iso, today
from freedays._sync import SyncUnavailableError
from freedays.tests.test_sync import FakeRemote


def _future() -> str:
    return to_iso(today() + timedelta(days=30))


def test_status_on_an_empty_pool(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["status"]) == 0
    assert "35 of 35 free days left" in capsys.readouterr().out


def test_check_exits_one_when_the_day_is_not_free(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["check"]) == 1
    assert "normal rules apply" in capsys.readouterr().out


def test_mark_then_check_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["mark", "today"]) == 0
    capsys.readouterr()
    assert main(["check", "today"]) == 0
    assert "free" in capsys.readouterr().out


def test_mark_reports_what_is_left(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["mark", "tomorrow"]) == 0
    assert "34 left" in capsys.readouterr().out


def test_mark_accepts_an_optional_reason(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["mark", _future(), "--reason", "wedding"]) == 0
    assert "is now a free day" in capsys.readouterr().out


def test_marking_a_past_day_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    yesterday = to_iso(today() - timedelta(days=1))
    assert main(["mark", yesterday]) == 1
    assert "already passed" in capsys.readouterr().err


def test_an_unparsable_date_is_told_apart_from_a_refusal(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Exit 2 means "I did not understand", not "no"."""
    assert main(["mark", "next tuesday"]) == 2
    assert "not a YYYY-MM-DD date" in capsys.readouterr().err


def test_release_of_a_future_day_says_it_was_refunded(
    capsys: pytest.CaptureFixture[str],
) -> None:
    day = _future()
    main(["mark", day])
    capsys.readouterr()
    assert main(["release", day]) == 0
    out = capsys.readouterr().out
    assert "refunded" in out
    assert "not refunded" not in out


def test_release_of_today_says_it_was_not_refunded(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main(["mark", "today"])
    capsys.readouterr()
    assert main(["release", "today"]) == 0
    assert "not refunded" in capsys.readouterr().out


def test_releasing_a_day_that_is_not_free_is_refused(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["release", _future()]) == 1
    assert "not a free day" in capsys.readouterr().err


def test_status_lists_days_booked_ahead(capsys: pytest.CaptureFixture[str]) -> None:
    day = _future()
    main(["mark", day])
    capsys.readouterr()
    main(["status"])
    assert f"booked ahead: {day}" in capsys.readouterr().out


def test_status_says_when_today_is_free(capsys: pytest.CaptureFixture[str]) -> None:
    main(["mark", "today"])
    capsys.readouterr()
    main(["status"])
    assert "every gate is standing down" in capsys.readouterr().out


def test_status_accepts_a_year(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["status", "--year", "2030"]) == 0
    assert "2030: 35 of 35" in capsys.readouterr().out


def test_sync_reports_success(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("freedays._sync.firebase_client_for", lambda _app: FakeRemote())
    assert main(["sync"]) == 0
    assert "pool synced" in capsys.readouterr().out


def test_sync_failure_is_reported_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def _refuse() -> None:
        msg = "no credentials on this machine"
        raise SyncUnavailableError(msg)

    monkeypatch.setattr("freedays._sync.get_client", _refuse)
    assert main(["sync"]) == 1
    assert "no credentials" in capsys.readouterr().err


def test_a_missing_subcommand_is_rejected() -> None:
    with pytest.raises(SystemExit):
        main([])


def test_sync_quiet_reports_success(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("freedays._sync.firebase_client_for", lambda _app: FakeRemote())
    assert main(["sync-quiet"]) == 0
    assert "pool synced" in capsys.readouterr().out


def test_sync_quiet_exits_zero_when_there_is_no_remote(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The timer must not go red just because the machine is offline."""

    def _refuse() -> None:
        msg = "no credentials on this machine"
        raise SyncUnavailableError(msg)

    monkeypatch.setattr("freedays._sync.get_client", _refuse)
    assert main(["sync-quiet"]) == 0
    assert "no remote available" in capsys.readouterr().out
