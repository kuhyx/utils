# Copyright (c) 2026 Krzysztof Rudnicki
"""The path-unit drop-ins follow the set of game folders, and only then reload."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from feedback_inbox._units import (
    SYNC_PATH,
    WATCH_PATH,
    desired,
    run_systemctl,
    sync_units,
)
from feedback_inbox.tests.test_support import make_bundle

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from feedback_inbox._paths import Paths


class _Systemctl:
    def __init__(self, code: int = 0) -> None:
        self.calls: list[list[str]] = []
        self.code = code

    def __call__(self, args: Sequence[str]) -> int:
        self.calls.append(list(args))
        return self.code


def test_desired_lists_feedback_and_binaries_dirs(paths: Paths) -> None:
    make_bundle(paths.data_root, game="cleanup-plate")
    (paths.data_root / "dread-grid_binaries").mkdir()
    wanted = desired(paths.data_root, paths.unit_dir)
    watch = wanted[paths.unit_dir / f"{WATCH_PATH}.d" / "dirs.conf"]
    sync = wanted[paths.unit_dir / f"{SYNC_PATH}.d" / "dirs.conf"]
    feedback = paths.data_root / "cleanup-plate_binaries" / "feedback"
    assert f"PathChanged={feedback}\n" in watch
    assert "dread-grid" not in watch
    assert f"PathChanged={paths.data_root}/cleanup-plate_binaries\n" in sync
    assert f"PathChanged={paths.data_root}/dread-grid_binaries\n" in sync


def test_sync_writes_reloads_and_restarts_once(paths: Paths) -> None:
    make_bundle(paths.data_root)
    ctl = _Systemctl()
    assert sync_units(paths.data_root, paths.unit_dir, ctl) is True
    assert ctl.calls == [
        ["daemon-reload"],
        ["restart", WATCH_PATH, SYNC_PATH],
    ]
    again = _Systemctl()
    assert sync_units(paths.data_root, paths.unit_dir, again) is False
    assert again.calls == []


def test_new_game_triggers_a_rewrite(paths: Paths) -> None:
    make_bundle(paths.data_root, game="cleanup-plate")
    sync_units(paths.data_root, paths.unit_dir, _Systemctl())
    make_bundle(paths.data_root, game="dread-grid")
    ctl = _Systemctl()
    assert sync_units(paths.data_root, paths.unit_dir, ctl) is True
    text = (paths.unit_dir / f"{WATCH_PATH}.d" / "dirs.conf").read_text(
        encoding="utf-8"
    )
    assert "dread-grid_binaries/feedback" in text


def test_systemctl_failure_is_an_error(paths: Paths) -> None:
    make_bundle(paths.data_root)
    ctl = _Systemctl(code=1)
    with pytest.raises(RuntimeError, match="daemon-reload"):
        sync_units(paths.data_root, paths.unit_dir, ctl)
    assert ctl.calls == [["daemon-reload"]]


def test_run_systemctl_uses_the_user_manager(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seen: list[list[str]] = []

    class _Done:
        returncode = 3

    def fake_run(cmd: list[str], *, check: bool) -> _Done:
        assert check is False
        seen.append(cmd)
        return _Done()

    monkeypatch.setattr("feedback_inbox._units.subprocess.run", fake_run)
    assert run_systemctl(["restart", "x"]) == 3
    assert seen == [["/usr/bin/systemctl", "--user", "restart", "x"]]
