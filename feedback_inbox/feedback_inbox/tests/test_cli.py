# Copyright (c) 2026 Krzysztof Rudnicki
"""The command line: run, sync, exit codes, lock."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from feedback_inbox import __main__ as entry
from feedback_inbox._cli import main
from feedback_inbox._inbox import MARKER
from feedback_inbox._paths import Paths, resolve_paths
from feedback_inbox.tests.test_support import FakeTodo, make_bundle

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


def test_run_imports_and_exits_zero(
    paths: Paths, caplog: pytest.LogCaptureFixture
) -> None:
    bundle = make_bundle(paths.data_root)
    todo = FakeTodo()
    with caplog.at_level(logging.INFO):
        assert main(["run", "--wait", "0"], client=todo) == 0
    assert (bundle / MARKER).exists()
    assert len(todo.calls) == 1
    assert "imported" in caplog.text
    assert main(["run", "--wait", "0"], client=todo) == 0
    assert len(todo.calls) == 1


def test_run_fails_loudly_when_todo_is_down(
    paths: Paths, caplog: pytest.LogCaptureFixture
) -> None:
    bundle = make_bundle(paths.data_root)
    assert main(["run", "--wait", "0"], client=FakeTodo(fail=True)) == 1
    assert not (bundle / MARKER).exists()
    assert "todo down" in caplog.text


def test_run_pending_is_not_an_error(paths: Paths) -> None:
    make_bundle(paths.data_root, entry=False)
    assert main(["run", "--wait", "0"], client=FakeTodo()) == 0


def test_run_builds_the_real_client_from_paths(paths: Paths) -> None:
    make_bundle(paths.data_root)
    assert main(["run", "--wait", "0"]) == 1


def test_run_with_nothing_to_do_needs_no_token(paths: Paths) -> None:
    assert main(["run", "--wait", "0"]) == 0


def test_run_takes_the_lock_file(paths: Paths) -> None:
    make_bundle(paths.data_root)
    assert main(["run", "--wait", "0"], client=FakeTodo()) == 0
    assert paths.lock_file.exists()


def test_sync_command(paths: Paths) -> None:
    make_bundle(paths.data_root)
    calls: list[list[str]] = []

    def fake(args: Sequence[str]) -> int:
        calls.append(list(args))
        return 0

    assert main(["sync"], systemctl=fake) == 0
    assert calls[0] == ["daemon-reload"]


def test_sync_failure_exit_code(paths: Paths, caplog: pytest.LogCaptureFixture) -> None:
    make_bundle(paths.data_root)
    assert main(["sync"], systemctl=lambda _a: 1) == 1
    assert "daemon-reload" in caplog.text


def test_usage_error() -> None:
    with pytest.raises(SystemExit):
        main([])


def test_real_paths_are_under_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("feedback_inbox._paths.Path.home", lambda: tmp_path)
    real = resolve_paths()
    assert real.data_root == tmp_path / "data"
    assert real.token_file == tmp_path / ".config" / "feedback-inbox" / "token"
    assert real.unit_dir == tmp_path / ".config" / "systemd" / "user"
    assert real.mcp_url == "http://127.0.0.1:8735/mcp"
    given = Paths.under(tmp_path)
    assert resolve_paths(given) is given


def test_module_entry_point(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["feedback-inbox", "run", "--wait", "0"])
    assert entry.run() == 0
