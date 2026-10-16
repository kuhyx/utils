# Copyright (c) 2026 Krzysztof Rudnicki
"""The command line: add, remove, list, check, sync."""

from __future__ import annotations

from datetime import timedelta
import runpy

import pytest

from sickdays._cli import main
from sickdays._day import to_iso, today
from sickdays._sync import SyncUnavailableError
from sickdays.tests.test_sync import FakeRemote


def _future() -> str:
    return to_iso(today() + timedelta(days=30))


def _refuse() -> None:
    msg = "no credentials on this machine"
    raise SyncUnavailableError(msg)


def test_list_on_an_empty_pool(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["list"]) == 0
    assert "no sick days" in capsys.readouterr().out


def test_add_defaults_to_today(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["add"]) == 0
    assert f"{to_iso(today())} is now a sick day" in capsys.readouterr().out
    assert main(["check"]) == 0


def test_list_marks_today(capsys: pytest.CaptureFixture[str]) -> None:
    main(["add", "today"])
    main(["add", _future()])
    capsys.readouterr()
    assert main(["list"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out == [f"{to_iso(today())}  (today)", _future()]


def test_remove_makes_the_day_normal(capsys: pytest.CaptureFixture[str]) -> None:
    main(["add", "tomorrow"])
    assert main(["remove", "tomorrow"]) == 0
    assert "normal day again" in capsys.readouterr().out
    assert main(["check", "tomorrow"]) == 1


def test_a_past_day_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    yesterday = to_iso(today() - timedelta(days=1))
    assert main(["add", yesterday]) == 1
    assert "already passed" in capsys.readouterr().err
    assert main(["remove", yesterday]) == 1


def test_removing_a_normal_day_is_refused(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["remove", _future()]) == 1
    assert "not a sick day" in capsys.readouterr().err


def test_a_free_day_is_refused(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sickdays._api.free_day_predicate", lambda: lambda _d: True)
    assert main(["add", _future()]) == 1
    assert "is a free day" in capsys.readouterr().err


def test_an_unparsable_date_exits_two(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["add", "next tuesday"]) == 2
    assert "not a YYYY-MM-DD date" in capsys.readouterr().err


def test_a_missing_subcommand_is_rejected() -> None:
    with pytest.raises(SystemExit):
        main([])


def test_sync_reports_success(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sickdays._sync.firebase_client_for", lambda _app: FakeRemote())
    assert main(["sync"]) == 0
    assert "pool synced" in capsys.readouterr().out


def test_sync_failure_exits_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sickdays._sync.get_client", _refuse)
    assert main(["sync"]) == 1
    assert "no credentials" in capsys.readouterr().err


def test_sync_quiet_exits_zero_either_way(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sickdays._sync.firebase_client_for", lambda _app: FakeRemote())
    assert main(["sync-quiet"]) == 0
    assert "pool synced" in capsys.readouterr().out
    monkeypatch.setattr("sickdays._sync.get_client", _refuse)
    assert main(["sync-quiet"]) == 0
    assert "no remote available" in capsys.readouterr().out


def test_python_dash_m_runs_the_cli(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.argv", ["sickdays", "list"])
    with pytest.raises(SystemExit) as exited:
        runpy.run_module("sickdays", run_name="__main__")
    assert exited.value.code == 0
    assert "no sick days" in capsys.readouterr().out
