"""Tests for the haiku -> Ollama -> fail-open requirement-list checker."""

from __future__ import annotations

import json
from typing import Any
import urllib.error

import pytest

from leetcode_coach import claude_cli, local_backend, req_check, toolbox
from leetcode_coach.tests._shared import FIXTURE_TOOLBOX

STATEMENT = "# 268. Missing Number\nn distinct numbers in [0, n]; find the missing one."


class _Haiku:
    """A stand-in for `claude_cli.ask` that always gives the same answer."""

    def __init__(self, answer: object) -> None:
        self.text = answer if isinstance(answer, str) else json.dumps(answer)
        self.calls: list[tuple[list[str], str]] = []

    def __call__(self, args: list[str], prompt: str, **_kw: object) -> dict[str, Any]:
        self.calls.append((args, prompt))
        return {"result": self.text, "_stderr": ""}


def _haiku(answer: object) -> _Haiku:
    return _Haiku(answer)


def _ollama(monkeypatch: pytest.MonkeyPatch, text: str | Exception) -> list[Any]:
    sent: list[Any] = []

    def chat(messages: list[dict[str, str]], **_kw: object) -> local_backend.LocalReply:
        sent.append(messages)
        if isinstance(text, Exception):
            raise text
        return local_backend.LocalReply(text, 1.0, 10)

    monkeypatch.setattr(local_backend, "chat", chat)
    return sent


@pytest.mark.parametrize(
    ("text", "obj"),
    [
        ('{"verdict": "pass"}', {"verdict": "pass"}),
        ('```json\n{"code": true}\n```', {"code": True}),
        ('Sure! {"a": 1} hope that helps {"b": 2}', {"a": 1}),
        ("no json here", None),
        ("{broken", None),
        ("[1, 2]", None),
    ],
)
def test_extract_json(text: str, obj: object) -> None:
    assert req_check.extract_json(text) == obj


VOCAB = toolbox.load_safe(FIXTURE_TOOLBOX).properties


@pytest.mark.parametrize(
    ("obj", "expected"),
    [
        ({"verdict": "pass", "missing": []}, ("pass", ())),
        ({"verdict": "pass"}, ("pass", ())),
        (
            {"verdict": "incomplete", "missing": ["self-inverse", "XOR", 4, "nope"]},
            ("incomplete", ("self-inverse",)),
        ),
        ({"verdict": "incomplete", "missing": ["XOR"]}, None),
        ({"verdict": "maybe", "missing": []}, None),
        ({"verdict": "incomplete", "missing": "self-inverse"}, None),
        (None, None),
    ],
)
def test_parse_verdict_keeps_only_vocabulary_properties(
    obj: object, expected: tuple[str, tuple[str, ...]] | None
) -> None:
    got = req_check.parse_verdict(obj, VOCAB)
    assert (got if got is None else (got.verdict, got.missing)) == expected


def test_the_prompt_carries_statement_list_and_vocabulary() -> None:
    prompt = req_check.check_prompt(STATEMENT, "req: one pass", toolbox.load_safe())
    assert STATEMENT in prompt
    assert "req: one pass" in prompt
    assert "self-inverse: applying it twice" in prompt
    assert "leetcode.com/problems" not in prompt


def test_haiku_answers_first(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = _ollama(monkeypatch, "unused")
    ask = _haiku({"verdict": "incomplete", "missing": ["constant-space", "XOR"]})
    got = req_check.check(STATEMENT, "req: loop", toolbox.load_safe(), ask)
    assert got == req_check.Check("incomplete", ("constant-space",), "haiku")
    args, _prompt = ask.calls[0]
    assert args[:2] == ["--model", "haiku"]
    assert "--resume" not in args
    assert sent == []


@pytest.mark.parametrize(
    "haiku_says",
    [
        "You've hit your session limit · resets 3pm",
        "not json at all",
        {"verdict": "incomplete", "missing": ["XOR"]},
    ],
)
def test_ollama_steps_in_when_haiku_cannot_answer(
    monkeypatch: pytest.MonkeyPatch, haiku_says: object
) -> None:
    _ollama(monkeypatch, '{"verdict": "pass", "missing": []}')
    got = req_check.check(STATEMENT, "req: x", toolbox.load_safe(), _haiku(haiku_says))
    assert got == req_check.Check("pass", (), "ollama")


@pytest.mark.parametrize(
    "ollama", [urllib.error.URLError("refused"), "garbage", ConnectionError("x")]
)
def test_both_down_fails_open_unverified(
    monkeypatch: pytest.MonkeyPatch, ollama: str | Exception
) -> None:
    _ollama(monkeypatch, ollama)
    got = req_check.check(STATEMENT, "req: x", toolbox.load_safe(), _haiku("nope"))
    assert got == req_check.Check("unverified", (), "none")


def test_an_empty_vocabulary_cannot_be_checked(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = _ollama(monkeypatch, "unused")
    ask = _haiku("unused")
    got = req_check.check(STATEMENT, "req: x", toolbox.Toolbox(), ask)
    assert got.verdict == "unverified"
    assert ask.calls == []
    assert sent == []


def test_the_default_asker_is_the_claude_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    ask = _haiku({"verdict": "pass"})
    monkeypatch.setattr(claude_cli, "ask", ask)
    assert req_check.check(STATEMENT, "req: x", toolbox.load_safe()).via == "haiku"
    assert ask.calls[0][0][:2] == ["--model", "haiku"]


@pytest.mark.parametrize(
    ("haiku_says", "ollama", "is_code"),
    [
        ({"code": True}, "unused", True),
        ({"code": False}, "unused", False),
        ("broken", '{"code": true}', True),
        ("broken", '{"code": "yes"}', False),
        ("broken", urllib.error.URLError("down"), False),
    ],
)
def test_model_code_classifier_fails_open_to_not_code(
    monkeypatch: pytest.MonkeyPatch,
    haiku_says: object,
    ollama: str | Exception,
    *,
    is_code: bool,
) -> None:
    _ollama(monkeypatch, ollama)
    assert req_check.looks_like_code("x ^ y", _haiku(haiku_says)) is is_code


class _Model:
    """The tutor's ``ask_model(system, prompt, schema)``: a parsed dict, or a raise."""

    def __init__(self, answer: dict[str, Any] | Exception) -> None:
        self.answer = answer
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def __call__(
        self, system: str, prompt: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        self.calls.append((system, prompt, schema))
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def test_a_structured_model_function_answers_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent = _ollama(monkeypatch, "unused")
    ask = _Model({"verdict": "incomplete", "missing": ["constant-space", "XOR"]})
    got = req_check.check(STATEMENT, "req: loop", toolbox.load_safe(), ask)
    assert got == req_check.Check("incomplete", ("constant-space",), "model")
    system, prompt, schema = ask.calls[0]
    assert system == req_check.CHECK_SYSTEM
    assert "req: loop" in prompt
    assert schema == req_check.CHECK_SCHEMA
    assert sent == []


@pytest.mark.parametrize(
    "answer",
    [RuntimeError("model down"), {"verdict": "incomplete", "missing": ["XOR"]}, {}],
)
def test_ollama_steps_in_when_the_model_function_cannot_answer(
    monkeypatch: pytest.MonkeyPatch, answer: dict[str, Any] | Exception
) -> None:
    _ollama(monkeypatch, '{"verdict": "pass", "missing": []}')
    got = req_check.check(STATEMENT, "req: x", toolbox.load_safe(), _Model(answer))
    assert got == req_check.Check("pass", (), "ollama")


def test_a_structured_model_function_classifies_code() -> None:
    ask = _Model({"code": True})
    assert req_check.looks_like_code("x ^= i", ask) is True
    assert ask.calls[0][2] == req_check.CODE_SCHEMA


def test_a_model_function_with_no_schema_gets_a_bare_object_schema() -> None:
    ask = _Model({"ok": 1})
    got = req_check.ask_models("sys", "prompt", lambda obj: obj, ask)
    assert got == ({"ok": 1}, "model")
    assert ask.calls[0][2] == {"type": "object"}


def test_a_callable_without_a_signature_is_the_cli_style(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ollama(monkeypatch, "unused")
    monkeypatch.setattr(req_check.inspect, "signature", _no_signature)
    got = req_check.check(
        STATEMENT, "req: x", toolbox.load_safe(), _haiku({"verdict": "pass"})
    )
    assert got.via == "haiku"


def _no_signature(_fn: object) -> None:
    raise ValueError
