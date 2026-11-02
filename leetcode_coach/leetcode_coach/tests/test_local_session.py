"""Tests for the offline /leetcode session loop: fetch, GPU check, run."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any
import urllib.error

import pytest

from leetcode_coach import local_backend, local_coach, local_session, phase, toolbox
from leetcode_coach.tests._shared import SAFE, STATEMENT, FakeChat, completed

if TYPE_CHECKING:
    from pathlib import Path


def test_opening_message_and_quit() -> None:
    assert local_session.opening_message(["loops"]) == (
        "Start the session. What I'm stuck on: loops"
    )
    assert "not said" in local_session.opening_message([])
    assert local_session.is_quit(" Quit ")
    assert local_session.is_quit("exit")
    assert not local_session.is_quit("quitting is hard")


def test_fetch_failure_asks_for_a_paste(capsys: pytest.CaptureFixture[str]) -> None:
    got = local_session.fetch_statement(
        "x", lambda: "pasted", runner=lambda *_a, **_k: completed(2)
    )
    assert got == "pasted"
    assert capsys.readouterr().out == (
        "[could not fetch the problem: premium or unknown problem]\n"
        "Paste the statement and starter code, then an empty line:\n"
    )
    local_session.fetch_statement(
        "x", lambda: None, runner=lambda *_a, **_k: completed(1, err=" offline \n")
    )
    assert capsys.readouterr().out.startswith("[could not fetch the problem: offline]")
    ok = local_session.fetch_statement(
        "x", lambda: None, runner=lambda *_a, **_k: completed(0, STATEMENT)
    )
    assert ok == STATEMENT


def test_fetch_runs_the_fetcher_by_path() -> None:
    seen: list[list[str]] = []

    def run(cmd: list[str], **_k: Any) -> Any:
        seen.append(cmd)
        return completed(0, "s")

    local_session.fetch_statement("two-sum", lambda: None, runner=run)
    assert seen[0][0] == sys.executable
    assert seen[0][1].endswith("leetcode_coach/fetch_problem.py")
    assert seen[0][2] == "two-sum"


def test_confirm_gpu_asks_only_when_something_else_holds_vram(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(local_backend, "model_loaded", lambda: False)
    monkeypatch.setattr(local_backend, "gpu_hogs", lambda: [("game", 9000)])
    assert local_session.confirm_gpu(lambda _q: "y")
    assert capsys.readouterr().out == (
        "[the GPU is busy -- loading the local model would compete with:]\n"
        "    game  9000 MiB\n"
    )
    assert not local_session.confirm_gpu(lambda _q: "")
    monkeypatch.setattr(local_backend, "gpu_hogs", list)
    assert local_session.confirm_gpu(lambda _q: pytest.fail("asked"))
    monkeypatch.setattr(local_backend, "model_loaded", lambda: True)
    assert local_session.confirm_gpu(lambda _q: pytest.fail("asked"))


def _session(
    monkeypatch: pytest.MonkeyPatch,
    *,
    statement: str | None = STATEMENT,
    gpu_ok: bool = True,
    chat: Any = None,
) -> None:
    monkeypatch.setattr(local_session, "fetch_statement", lambda _p, _r: statement)
    monkeypatch.setattr(local_session, "confirm_gpu", lambda: gpu_ok)
    if chat is not None:
        real_start = local_coach.LocalCoach.start

        def start(
            text: str, history: list[dict[str, str]] | None = None
        ) -> local_coach.LocalCoach:
            coach = real_start(text, history)
            coach.chat = chat
            return coach

        monkeypatch.setattr(local_coach.LocalCoach, "start", start)


def test_run_coaches_until_quit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = FakeChat(SAFE, SAFE)
    _session(monkeypatch, chat=fake)
    blocks = iter(["hint", "quit"])
    assert local_session.run("two-sum", [], "Start.", lambda: next(blocks)) == 0
    out = capsys.readouterr().out
    assert out.startswith(f"[local: {local_backend.MODEL} via Ollama]\n\n...\n")
    assert out.count(SAFE) == 2
    assert fake.texts == []


def test_run_stops_without_a_statement_or_gpu(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _session(monkeypatch, statement=None)
    assert local_session.run("x", [], "Start.", lambda: None) == 1
    _session(monkeypatch, gpu_ok=False)
    assert local_session.run("x", [], "Start.", lambda: None) == 1
    assert capsys.readouterr().out == "[not loading the local model]\n"


def test_run_reports_an_unreachable_ollama(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def down(_m: object) -> object:
        msg = "refused"
        raise urllib.error.URLError(msg)

    _session(monkeypatch, chat=down)
    assert local_session.run("x", [], "Start.", lambda: None) == 1
    out = capsys.readouterr().out
    assert f"[Ollama is not reachable at {local_backend.OLLAMA_URL}: " in out
    assert out.endswith("[start it with: systemctl start ollama]\n")


def test_run_reports_a_context_overflow(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def full(_m: object) -> object:
        msg = "too long"
        raise local_backend.ContextOverflowError(msg)

    _session(monkeypatch, chat=full)
    assert local_session.run("x", [], "Start.", lambda: None) == 1
    assert capsys.readouterr().out.endswith("[too long]\n")


def test_fetched_statement_never_asks_for_a_paste() -> None:
    ok = local_session.fetched_statement(
        "x", runner=lambda *_a, **_k: completed(0, STATEMENT)
    )
    assert ok == STATEMENT
    assert (
        local_session.fetched_statement("x", runner=lambda *_a, **_k: completed(2))
        is None
    )


def test_run_with_a_gate_holds_code_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = FakeChat(SAFE, SAFE)
    _session(monkeypatch, chat=fake)
    gate = phase.PhaseGate(tmp_path / "log.jsonl", toolbox.load_safe(), lambda: "s")
    blocks = iter(["function f(nums) {\n  return 0;\n}", "hint", "quit"])
    assert local_session.run("x", [], "Start.", lambda: next(blocks), gate=gate) == 0
    out = capsys.readouterr().out
    assert "[code held back: write the requirement list first" in out
    assert out.count(SAFE) == 2
    assert len(fake.prompts) == 2  # the code never reached the model
    assert gate.known == STATEMENT
