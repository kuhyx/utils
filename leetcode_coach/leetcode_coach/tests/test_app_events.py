"""The coach modules' side of the relay contract (DOCS-coach-relay.md 2 and 5).

New session-log events, sessions split at ``session_start``, the step-2
force that must open code, and the env/timeout seams the relay calls with.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from leetcode_coach import (
    claude_cli,
    local_backend,
    phase,
    req_check,
    session_log,
    toolbox,
)

if TYPE_CHECKING:
    from pathlib import Path

NEW_EVENTS = ("session_start", "grade", "chat", "session_end")


@pytest.mark.parametrize("event", NEW_EVENTS)
def test_the_app_events_are_part_of_the_contract(tmp_path: Path, event: str) -> None:
    path = tmp_path / "log.jsonl"
    session_log.append(path, event, sid="20261023-170448-5b71")
    assert session_log.read(path)[0]["event"] == event


def test_the_docstring_allows_new_names_only_with_the_reader() -> None:
    doc = " ".join((session_log.__doc__ or "").split())
    assert "never as a new event name" not in doc
    assert "new names only together with the reader" in doc


def test_current_is_everything_after_the_last_session_start() -> None:
    cli = [{"event": "req"}, {"event": "code"}]
    assert session_log.current(cli) == cli
    app = [
        {"event": "session_start", "sid": "a"},
        {"event": "code"},
        {"event": "session_start", "sid": "b"},
        {"event": "rung", "rung": "H1"},
    ]
    assert session_log.current([*cli, *app]) == app[2:]


def test_code_from_an_earlier_session_does_not_count(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    session_log.append(log, "code")
    assert session_log.has_code(log)
    session_log.append(log, "session_start", sid="s")
    assert not session_log.has_code(log)


def _grade(step: int, grade: str, *, forced: bool = False) -> dict[str, Any]:
    return {"event": "grade", "step": step, "grade": grade, "forced": forced}


def test_a_forced_step_two_opens_code() -> None:
    events = [{"event": "req_check", "verdict": "incomplete"}, _grade(2, "fail")]
    assert not phase.req_state(events).open
    forced = phase.req_state([*events, _grade(2, "fail", forced=True)])
    assert forced.open
    assert forced.forced
    assert not forced.accepted
    assert not phase.req_state([_grade(1, "pass", forced=True)]).open


def test_step_two_attempts_count_incomplete_lists_and_fail_grades() -> None:
    events = [
        {"event": "req_check", "verdict": "incomplete"},
        _grade(2, "partial"),
        _grade(2, "fail"),
        _grade(1, "fail"),
        {"event": "req_check", "verdict": "incomplete"},
    ]
    assert phase.step2_attempts(events) == 3


def test_a_force_is_not_a_step_two_try() -> None:
    """A force repeats the last try's grade (`fail`); it is no try itself.

    Measured against the live relay 2026-10-23: three named-a-tool fails and
    a force showed ``attempts: 4`` in the state.
    """
    fails = [_grade(2, "fail"), _grade(2, "fail"), _grade(2, "fail")]
    assert phase.step2_attempts([*fails, _grade(2, "fail", forced=True)]) == 3


def _gate(log: Path, answers: list[bool] | None = None) -> phase.PhaseGate:
    asked: list[str] = []

    def ask(_args: list[str], prompt: str, **_kw: object) -> dict[str, Any]:
        asked.append(prompt)
        return {"result": json.dumps({"code": (answers or [False]).pop(0)})}

    gate = phase.PhaseGate(log, toolbox.load_safe(), lambda: "statement", ask)
    gate.known = "statement"
    return gate


def test_screen_takes_a_verdict_already_reached(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    gate = _gate(log)
    session_log.append(log, "grade", step=2, grade="pass", forced=True)
    sent, note = gate.screen("a = b", is_code=True)
    assert sent == "a = b"
    assert note == ""
    assert session_log.read(log)[-1]["event"] == "code"
    assert gate.screen("x = y", is_code=False) == ("x = y", "")
    assert [e["event"] for e in session_log.read(log)].count("code") == 1


def test_screen_judges_only_the_current_session(tmp_path: Path) -> None:
    log = tmp_path / "log.jsonl"
    session_log.append(log, "req_check", verdict="pass", missing=[])
    session_log.append(log, "session_start", sid="s")
    sent, note = _gate(log).screen("const x = 1;")
    assert sent is None
    assert "requirement list first" in note


def test_property_line_is_public() -> None:
    box = toolbox.load_safe()
    prop = next(iter(box.properties))
    assert phase.property_line(prop, box).startswith(prop)


def test_ask_merges_the_extra_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = tmp_path / "claude"
    stub.write_text(
        '#!/bin/sh\nprintf \'{"result": "%s|%s|%s"}\' '
        '"$LEETCODE_COACH_LOG" "$CLAUDE_TTY_FIX_OFF" "$KEPT"\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)
    monkeypatch.setenv("LEETCODE_CLAUDE_BIN", str(stub))
    monkeypatch.setenv("KEPT", "yes")
    reply = claude_cli.ask([], "hi", env={"LEETCODE_COACH_LOG": "/x.jsonl"})
    assert reply["result"] == "/x.jsonl|1|yes"


def test_ask_models_is_public_and_bounds_the_local_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[float] = []

    def local(messages: list[dict[str, str]], *, timeout: float) -> object:
        seen.append(timeout)
        return local_backend.LocalReply('{"ok": 1}', 1.0, 1)

    monkeypatch.setattr(local_backend, "chat", local)

    def limit(*_a: object, **_kw: object) -> dict[str, Any]:
        return {"result": "You've hit your session limit"}

    got = req_check.ask_models("sys", "p", lambda o: o, limit)
    assert got == ({"ok": 1}, "ollama")
    assert seen == [req_check.LOCAL_TIMEOUT_S]
    assert req_check.LOCAL_TIMEOUT_S + req_check.HAIKU_TIMEOUT_S < 280


def test_local_chat_takes_a_timeout() -> None:
    timeouts: list[float] = []

    def post(_url: str, _payload: object, timeout: float) -> dict[str, Any]:
        timeouts.append(timeout)
        return {"message": {"content": "hi"}}

    reply = local_backend.chat([{"role": "user", "content": "x"}], post=post, timeout=7)
    assert reply.text == "hi"
    local_backend.chat([{"role": "user", "content": "x"}], post=post)
    assert timeouts == [7, local_backend.REQUEST_TIMEOUT_S]
