"""Tests for the one `claude -p` call shared by the REPL and the checker."""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import TYPE_CHECKING

from leetcode_coach import claude_cli

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> Path:
    stub = tmp_path / "claude"
    stub.write_text(body, encoding="utf-8")
    stub.chmod(0o755)
    monkeypatch.setenv("LEETCODE_CLAUDE_BIN", str(stub))
    return stub


def test_ask_parses_a_failing_claude_stub(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = json.dumps({"is_error": True, "result": "You've hit your session limit"})
    (tmp_path / "out.json").write_text(body, encoding="utf-8")
    stub = _stub(
        tmp_path,
        monkeypatch,
        f"#!/bin/sh\ncat {tmp_path / 'out.json'}\necho boom >&2\nexit 1\n",
    )
    reply = claude_cli.ask([], "hi")
    assert claude_cli.is_limit_hit(reply)
    assert reply["_stderr"] == "boom"
    stub.write_text("#!/bin/sh\necho not-json\nexit 3\n", encoding="utf-8")
    assert claude_cli.ask([], "hi")["result"].startswith("[claude exited 3]")
    stub.write_text("#!/bin/sh\necho '[1]'\n", encoding="utf-8")
    assert claude_cli.ask([], "hi") == {"_stderr": ""}


def test_ask_passes_args_then_the_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub(tmp_path, monkeypatch, '#!/bin/sh\nprintf \'{"result": "%s"}\' "$*"\n')
    got = claude_cli.ask(["--model", "haiku"], "go")["result"]
    assert got == "-p --model haiku --output-format json go"


def test_a_missing_binary_is_an_error_reply_not_a_crash() -> None:
    reply = claude_cli.ask([], "hi")
    assert reply["result"].startswith("[claude could not run")


def test_a_hung_claude_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    def hang(*_a: object, **_kw: object) -> subprocess.CompletedProcess[str]:
        msg = "claude"
        raise subprocess.TimeoutExpired(msg, 1.0)

    monkeypatch.setattr(subprocess, "run", hang)
    assert claude_cli.ask([], "hi", timeout=1.0)["result"].startswith(
        "[claude could not run"
    )


def test_the_binary_is_looked_up_per_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEETCODE_CLAUDE_BIN", "")
    monkeypatch.setattr(shutil, "which", lambda _n: "/opt/claude")
    assert claude_cli.claude_bin() == "/opt/claude"
    monkeypatch.setattr(shutil, "which", lambda _n: None)
    assert claude_cli.claude_bin() == "claude"
