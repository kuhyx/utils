from __future__ import annotations

import io
import json
import sys
from typing import TYPE_CHECKING

import pytest

from omniroute_offload import _hook as hook
from omniroute_offload import _privacy as privacy

if TYPE_CHECKING:
    from pathlib import Path


def _run(monkeypatch: pytest.MonkeyPatch, payload: object) -> str:
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    assert hook.main() == 0
    return out.getvalue()


def _read(path: Path, **extra: object) -> dict[str, object]:
    return {"tool_name": "Read", "tool_input": {"file_path": str(path), **extra}}


def test_big_public_file_gets_nudge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = tmp_path / "doc.md"
    doc.write_text("x" * (hook.MIN_BYTES + 1))
    out = json.loads(_run(monkeypatch, _read(doc)))
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert "free-llm" in ctx
    assert str(doc) in ctx


def test_small_file_is_silent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    doc = tmp_path / "doc.md"
    doc.write_text("small")
    assert _run(monkeypatch, _read(doc)) == ""


def test_ranged_read_is_silent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    doc = tmp_path / "doc.md"
    doc.write_text("x" * (hook.MIN_BYTES + 1))
    assert _run(monkeypatch, _read(doc, limit=50)) == ""


def test_private_file_is_silent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = tmp_path / "doc.md"
    doc.write_text("x" * (hook.MIN_BYTES + 1))
    monkeypatch.setattr(privacy, "file_refusal", lambda _p, home: "private")
    assert _run(monkeypatch, _read(doc)) == ""


@pytest.mark.parametrize(
    "payload",
    [
        "not a dict",
        {"tool_name": "Bash", "tool_input": {}},
        {"tool_name": "Read"},
        {"tool_name": "Read", "tool_input": {"file_path": "/nonexistent/x"}},
    ],
)
def test_odd_input_is_silent(monkeypatch: pytest.MonkeyPatch, payload: object) -> None:
    assert _run(monkeypatch, payload) == ""


def test_invalid_json_is_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("{oops"))
    assert hook.main() == 0
