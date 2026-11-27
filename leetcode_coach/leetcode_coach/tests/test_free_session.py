"""The REPL's usage-limit path: OmniRoute ``free-best`` first, Ollama only after.

kuhy 2026-11-27 (part 9005c9b4-2): a Claude usage limit hands the session to
the free models, through the same no-solution gate, so a leaking draft is
rejected and regenerated, never printed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from leetcode_coach import (
    leetcode_repl,
    local_backend,
    local_session,
    omniroute_backend,
)
from leetcode_coach.tests._fake_omniroute import FakeOmniRoute
from leetcode_coach.tests._shared import LEAK, SAFE, STATEMENT, FakeChat

if TYPE_CHECKING:
    import pytest


def _statement(monkeypatch: pytest.MonkeyPatch, *, gpu_ok: bool = True) -> list[str]:
    asked: list[str] = []
    monkeypatch.setattr(local_session, "fetch_statement", lambda _p, _r: STATEMENT)

    def confirm() -> bool:
        asked.append("gpu")
        return gpu_ok

    monkeypatch.setattr(local_session, "confirm_gpu", confirm)
    return asked


def test_free_run_answers_through_omniroute_without_touching_the_gpu(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    asked = _statement(monkeypatch)
    with FakeOmniRoute([SAFE]) as fake:
        monkeypatch.setenv(omniroute_backend.URL_ENV, fake.url)
        got = local_session.run("two-sum", [], "Start.", lambda: None, free=True)
    out = capsys.readouterr().out
    assert got == 0
    assert out.startswith("[free: free-best via OmniRoute]\n\n...\n")
    assert SAFE in out
    assert asked == []


def test_a_leaking_free_draft_is_regenerated_and_never_printed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _statement(monkeypatch)
    with FakeOmniRoute([LEAK, SAFE]) as fake:
        monkeypatch.setenv(omniroute_backend.URL_ENV, fake.url)
        assert local_session.run("two-sum", [], "Start.", lambda: None, free=True) == 0
    out = capsys.readouterr().out
    assert "seen.set" not in out
    assert SAFE in out
    assert len(fake.bodies) == 2


def test_a_dead_gateway_falls_through_to_ollama_after_the_gpu_check(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    asked = _statement(monkeypatch)
    ollama = FakeChat(SAFE)
    monkeypatch.setattr(local_backend, "chat", lambda m, **_k: ollama(m))
    assert local_session.run("two-sum", [], "Start.", lambda: None, free=True) == 0
    out = capsys.readouterr().out
    assert f"[OmniRoute down: local {local_backend.MODEL} via Ollama]" in out
    assert SAFE in out
    assert asked == ["gpu"]


def test_the_gpu_is_asked_once_per_free_session(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    asked = _statement(monkeypatch)
    ollama = FakeChat(SAFE, SAFE)
    monkeypatch.setattr(local_backend, "chat", lambda m, **_k: ollama(m))
    blocks = iter(["hint", "quit"])
    assert (
        local_session.run("two-sum", [], "Start.", lambda: next(blocks), free=True) == 0
    )
    assert asked == ["gpu"]
    assert capsys.readouterr().out.count("OmniRoute down") == 1


def test_a_refused_gpu_ends_the_free_session_once_omniroute_is_down(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _statement(monkeypatch, gpu_ok=False)
    assert local_session.run("two-sum", [], "Start.", lambda: None, free=True) == 1
    out = capsys.readouterr().out
    assert "[not loading the local model]" in out
    assert "neither OmniRoute nor Ollama answered" in out


def test_the_repl_hands_a_limit_to_the_free_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(leetcode_repl, "ask", lambda *_a: {"api_error_status": 429})
    handed: dict[str, Any] = {}

    def fake_run(*_a: object, **kw: object) -> int:
        handed.update(kw)
        return 0

    monkeypatch.setattr(local_session, "run", fake_run)
    assert leetcode_repl.run_claude("sonnet", ["two-sum"]) == 0
    assert handed["free"] is True


def test_local_mode_stays_on_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    """``leetcode --local`` is the explicit offline choice: no gateway."""
    handed: dict[str, Any] = {}

    def fake_run(*_a: object, **kw: object) -> int:
        handed.update(kw)
        return 0

    monkeypatch.setattr(local_session, "run", fake_run)
    assert leetcode_repl.main(["--local", "two-sum"]) == 0
    assert handed.get("free", False) is False
