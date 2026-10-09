# Copyright (c) 2026 Krzysztof Rudnicki
"""``python -m earned_time maturity``: table, JSON, and the paths it reads."""

from __future__ import annotations

from datetime import date, datetime, time
import json
import runpy
import sys
from typing import TYPE_CHECKING

import pytest

import earned_time
from earned_time import LEETCODE, READING, Earner, entry_signature
from earned_time import _cli as cli

if TYPE_CHECKING:
    from pathlib import Path

KEY = b"test-key"
DAY = date(2026, 10, 9)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fake home with a key and one LeetCode solve on DAY."""
    key = tmp_path / "hmac.key"
    key.write_bytes(KEY)
    monkeypatch.setattr(cli, "KEY_FILE", key)
    monkeypatch.setattr(cli, "home", lambda: tmp_path)
    stamp = datetime.combine(DAY, time(12)).astimezone().timestamp()
    row: dict[str, object] = {
        "kind": "credit",
        "entry_id": "ac:1",
        "day": DAY.isoformat(),
        "amount": 1,
        "detail": {"submitted_at": str(stamp)},
    }
    ledger = tmp_path / str(LEETCODE.ledger)
    ledger.parent.mkdir(parents=True)
    entries = [{**row, "hmac": entry_signature(row, KEY)}]
    ledger.write_text(json.dumps({"entries": entries}), encoding="utf-8")
    return tmp_path


def test_table(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["maturity", "--day", DAY.isoformat()]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == f"gate maturity on {DAY}"
    assert out[1].split()[:3] == ["gate", "level", "days"]
    rows = {line.split()[0]: line for line in out[2:-1]}
    assert set(rows) == {
        "workout",
        "leetcode",
        "reading",
        "anki",
        "automation:anki_guard",
        "automation:automation_tutor",
    }
    assert rows["leetcode"].split()[1:5] == ["maturing", "1", str(DAY), str(DAY)]
    assert "not in the registry on 2026-10-09" in rows["anki"]
    assert "could not check: ledger" not in rows["reading"]
    assert rows["reading"].endswith(
        "no verified credit but confirmed_on 2026-10-02: "
        "fail closed, penalty from 2026-10-03"
    )
    assert out[-1].startswith("not classified (no earn-back): diet-guard")


def test_json(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["maturity", "--json", "--day", DAY.isoformat()]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["day"] == DAY.isoformat()
    assert payload["not_classified"] == list(cli.NOT_CLASSIFIED)
    gates = {g["gate"]: g for g in payload["gates"]}
    assert gates["leetcode"]["first_credit"] == DAY.isoformat()
    assert gates["leetcode"]["checked"] is True
    assert gates["reading"]["penalty_from"] == READING.penalty_from.isoformat()
    # No reading ledger, but confirmed_on is set: fail closed, not lifted.
    assert gates["reading"]["penalty_start"] == "2026-10-03"
    assert gates["anki"]["penalty_start"] is None
    assert gates["anki"]["last_credit"] is None


def test_default_day_and_unregistered_earners(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    consumer = Earner(name="piano", label="piano", gaming_minutes=1, shutdown_minutes=1)
    monkeypatch.setattr(earned_time, "EARNERS", (consumer, LEETCODE))
    assert cli.main(["maturity"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert [line.split()[0] for line in lines[2:-1]] == [
        "leetcode",
        "workout",
        "reading",
        "automation",
    ]


def test_render_table_pads_all_but_the_reasons() -> None:
    verdict = earned_time.Maturity(
        name="x",
        level="new",
        reasons=("a", "b"),
        credit_days=0,
        credit_rows=0,
        first_credit=None,
        last_credit=None,
        confirmed_on=None,
        penalty_from=None,
        penalty_start=None,
        checked=True,
    )
    table = cli.render_table([("x", verdict)]).splitlines()
    assert table[1].split() == ["x", "new", "0", *["-"] * 5, "a;", "b"]
    assert len(table) == 2


def test_home_is_the_users_home() -> None:
    assert cli.home().is_absolute()


def test_python_dash_m(
    home: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["earned_time", "maturity", "--json"])
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("earned_time", run_name="__main__")
    assert exit_info.value.code == 0
    assert json.loads(capsys.readouterr().out)["gates"]
