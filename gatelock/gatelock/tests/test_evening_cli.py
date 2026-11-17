# Copyright (c) 2026 Krzysztof Rudnicki
"""The chain's process edges: gate subprocesses, production paths, the unit."""

from __future__ import annotations

from pathlib import Path
import runpy
import subprocess
import sys
from types import SimpleNamespace
from unittest import mock

import pytest

from gatelock import evening_chain as chain


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
