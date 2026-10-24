"""State file round-trip, artefact root and the module entry point."""

from __future__ import annotations

import re
import runpy
import sys
from pathlib import Path

import pytest

from flutter_web_drive import state


def test_round_trip_and_clear(tmp_path: Path) -> None:
    assert state.load(tmp_path, "a") is None
    saved = state.State(unit="u", cdp_port=1, url="http://x/", profile="/p")
    state.save(tmp_path, "a", saved)
    assert state.load(tmp_path, "a") == saved
    state.clear(tmp_path, "a")
    state.clear(tmp_path, "a")
    assert state.load(tmp_path, "a") is None


def test_artefact_root_defaults_under_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("FWD_ARTEFACTS", raising=False)
    assert state.artefact_root() == Path.home() / "data" / "claude-scratch" / "e2e"
    monkeypatch.setenv("FWD_ARTEFACTS", str(tmp_path))
    assert state.artefact_root() == tmp_path


def test_stamp_is_sortable() -> None:
    assert re.fullmatch(r"\d{8}-\d{6}-\d{3}", state.stamp())


def test_module_entry_point_runs_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["flutter_web_drive", "--help"])
    with pytest.raises(SystemExit) as err:
        runpy.run_module("flutter_web_drive", run_name="__main__")
    assert err.value.code == 0
