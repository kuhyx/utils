# Copyright (c) 2026 Krzysztof Rudnicki
"""``evening_chain run``: order, skipping, exit codes, no spinning."""

from __future__ import annotations

from datetime import datetime, timedelta
import os
from pathlib import Path
import pwd
import runpy
import subprocess
import sys
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest import mock

import pytest

from gatelock import evening_chain as chain
from gatelock.tests.test_evening_rows import (
    EVENING,
    leetcode_row,
    pay_all,
    reading_row,
    seeded,
    tutor_row,
    write_ledger,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

CMD_OF = {tuple(cmd): rung for rung, cmd in chain.GATE_COMMANDS.items()}


class FakeGates:
    """Runner stand-in: records the rung run, pays it, returns scripted codes."""

    def __init__(
        self,
        sources: chain.Sources,
        codes: dict[str, list[int | None]] | None = None,
    ) -> None:
        self.sources = sources
        self.codes = codes or {}
        self.ran: list[str] = []
        self.timeouts: list[float] = []

    def __call__(self, cmd: Sequence[str], timeout_s: float) -> int | None:
        rung = CMD_OF[tuple(cmd)]
        self.ran.append(rung)
        self.timeouts.append(timeout_s)
        script = self.codes.get(rung)
        code = script.pop(0) if script else 0
        if code == 0:
            pays = {"reading": reading_row, "leetcode": leetcode_row}
            rows = [tutor_row(15)] if rung == "tutor" else [pays[rung]()]
            write_ledger(self.sources, rung, rows)
        return code


def _run(
    sources: chain.Sources,
    gates: Callable[[Sequence[str], float], int | None],
    now: datetime = EVENING,
) -> int:
    return chain.run(sources, lambda: now, gates)


def test_gate_commands_match_the_contract() -> None:
    py = "/usr/bin/python3"
    expected = {
        "reading": (py, "-m", "book_guard", "lock", "--production", "--evening"),
        "tutor": (py, "-m", "tutor.gate", "--production", "--evening"),
        "leetcode": (py, "-m", "leetcode_guard", "--production", "--evening"),
    }
    assert expected == chain.GATE_COMMANDS


def test_runs_book_then_tutor_then_leetcode(tmp_path: Path) -> None:
    sources = seeded(tmp_path)
    gates = FakeGates(sources)
    assert _run(sources, gates) == 0
    assert gates.ran == ["reading", "tutor", "leetcode"]


def test_paid_rungs_are_skipped(tmp_path: Path) -> None:
    sources = seeded(tmp_path)
    pay_all(sources)
    write_ledger(sources, "tutor", [])
    gates = FakeGates(sources)
    assert _run(sources, gates) == 0
    assert gates.ran == ["tutor"]


def test_nothing_pending_runs_nothing(tmp_path: Path) -> None:
    sources = seeded(tmp_path)
    pay_all(sources)
    gates = FakeGates(sources)
    assert _run(sources, gates) == 0
    assert gates.ran == []


def test_exit_10_stops_the_chain_with_exit_0(tmp_path: Path) -> None:
    sources = seeded(tmp_path)
    gates = FakeGates(sources, {"tutor": [10]})
    assert _run(sources, gates) == 0
    assert gates.ran == ["reading", "tutor"]


def test_exit_3_no_x_is_exit_3_at_once(tmp_path: Path) -> None:
    sources = seeded(tmp_path)
    gates = FakeGates(sources, {"reading": [3]})
    assert _run(sources, gates) == 3
    assert gates.ran == ["reading"]


def test_one_failing_gate_is_skipped_and_the_rest_run(tmp_path: Path) -> None:
    sources = seeded(tmp_path)
    gates = FakeGates(sources, {"reading": [7]})
    assert _run(sources, gates) == 1  # reading stays unpaid
    assert gates.ran == ["reading", "tutor", "leetcode"]


def test_two_failures_in_a_row_stop_with_exit_1(tmp_path: Path) -> None:
    sources = seeded(tmp_path)
    gates = FakeGates(sources, {"reading": [7], "tutor": [9]})
    assert _run(sources, gates) == 1
    assert gates.ran == ["reading", "tutor"]


def test_a_gate_that_exits_0_unpaid_never_spins(tmp_path: Path) -> None:
    sources = seeded(tmp_path)
    calls: list[str] = []

    def liar(cmd: Sequence[str], timeout_s: float) -> int | None:
        calls.append(CMD_OF[tuple(cmd)])
        return 0 if len(calls) < 50 else 99  # pays nothing

    assert _run(sources, liar) == 1
    assert calls == ["reading", "tutor"]


def test_stops_at_23_00_without_running_a_gate(tmp_path: Path) -> None:
    sources = seeded(tmp_path)
    gates = FakeGates(sources)
    assert _run(sources, gates, EVENING.replace(hour=23, minute=0)) == 0
    assert gates.ran == []


def test_gate_is_bounded_by_the_23_00_cutoff(tmp_path: Path) -> None:
    sources = seeded(tmp_path)
    gates = FakeGates(sources, {"reading": [None]})  # timed out at the deadline
    assert _run(sources, gates) == 0
    assert gates.ran == ["reading"]
    assert gates.timeouts == [timedelta(hours=2, minutes=30).total_seconds()]


def test_unchecked_rung_still_gets_its_gate(tmp_path: Path) -> None:
    sources = seeded(tmp_path)
    pay_all(sources)
    write_ledger(sources, "leetcode", []).write_text("{bad")
    gates = FakeGates(sources, {"leetcode": [7]})
    assert _run(sources, gates) == 1
    assert gates.ran == ["leetcode"]


def test_main_run_uses_the_injected_runner(tmp_path: Path) -> None:
    sources = seeded(tmp_path)
    pay_all(sources)
    gates = FakeGates(sources)
    code = chain.main(["run"], sources=sources, clock=lambda: EVENING, runner=gates)
    assert code == 0
    assert gates.ran == []


def test_subprocess_runner_returns_the_exit_code_with_the_timeout() -> None:
    done = SimpleNamespace(returncode=7)
    with mock.patch("gatelock.evening_chain.subprocess.run", return_value=done) as run:
        assert chain.subprocess_runner(("gate", "--x"), 12.5) == 7
    run.assert_called_once_with(("gate", "--x"), check=False, timeout=12.5)


def test_subprocess_runner_deadline_is_none() -> None:
    expired = subprocess.TimeoutExpired(("gate",), 1)
    with mock.patch("gatelock.evening_chain.subprocess.run", side_effect=expired):
        assert chain.subprocess_runner(("gate",), 1) is None


def test_subprocess_runner_unstartable_gate_is_a_failure() -> None:
    with mock.patch("gatelock.evening_chain.subprocess.run", side_effect=OSError):
        assert chain.subprocess_runner(("gate",), 1) == 127


def test_run_failing_to_evaluate_is_exit_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(_day: object) -> None:
        msg = "registry exploded"
        raise RuntimeError(msg)

    monkeypatch.setattr("earned_time.earners_for", boom)
    gates = FakeGates(seeded(tmp_path))
    code = chain.main(
        ["run"], sources=seeded(tmp_path), clock=lambda: EVENING, runner=gates
    )
    assert code == 1
    assert gates.ran == []


def test_production_sources_names_the_real_key_and_home() -> None:
    sources = chain.production_sources()
    assert str(sources.key_file) == "/etc/workout-locker/hmac.key"
    assert sources.home == Path.home()
    assert sources.free_log is None
    assert sources.sick_log is None


def test_module_entry_point_rejects_an_unknown_command() -> None:
    with (
        pytest.warns(RuntimeWarning),
        pytest.raises(SystemExit) as raised,
        mock.patch.object(sys, "argv", ["evening_chain", "bogus"]),
    ):
        runpy.run_module("gatelock.evening_chain", run_name="__main__")
    assert raised.value.code == 2


UNIT = Path(__file__).parents[2] / "systemd" / "evening-gates.service"


def test_unit_matches_the_contract() -> None:
    lines = UNIT.read_text(encoding="utf-8").splitlines()
    assert "Type=simple" in lines
    assert "Restart=no" in lines
    assert "Environment=DISPLAY=:0" in lines
    assert "Environment=XAUTHORITY=%h/.Xauthority" in lines
    assert "ExecStart=/usr/bin/python3 -m gatelock.evening_chain run" in lines
    assert "[Install]" not in lines


def test_live_ledgers_are_untouched_by_a_run(tmp_path: Path) -> None:
    home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    live = sorted((home / ".local" / "share").glob("*/ledger.json"))
    before = [(p, p.stat().st_mtime_ns) for p in live]
    sources = seeded(tmp_path)
    assert _run(sources, FakeGates(sources)) == 0
    assert [(p, p.stat().st_mtime_ns) for p in live] == before
