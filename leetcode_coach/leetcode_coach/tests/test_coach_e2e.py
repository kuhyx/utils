"""Scripted end-to-end runs of the req-first coach (TODO-coach.md "Build done").

The REPL runs in-process against a fake `claude` binary (LEETCODE_CLAUDE_BIN,
a real subprocess per turn) and a fake Ollama on a localhost port, with
kuhy's input scripted. Only the problem fetch is stubbed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from leetcode_coach import leetcode_repl, local_backend, local_session, report
from leetcode_coach.tests._fake_ollama import FakeOllama

if TYPE_CHECKING:
    from collections.abc import Iterator

FAKE_CLAUDE = Path(__file__).with_name("_fake_claude.py")
STATEMENT = (
    "# 268. Missing Number (Easy)\nn distinct numbers in [0, n]; return the missing "
    "one.\n\n## Starter code (javascript)\n```\n"
    "var missingNumber = function(nums) {\n};\n```\n"
)
CODE = "var missingNumber = function(nums) {\n  return 0;\n};"


def _script(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **script: Any) -> Path:
    root = tmp_path / "fake-claude"
    root.mkdir(exist_ok=True)
    for used in root.glob("*.used"):
        used.unlink()
    (root / "calls.jsonl").write_text("", encoding="utf-8")
    (root / "script.json").write_text(json.dumps(script), encoding="utf-8")
    monkeypatch.setenv("LEETCODE_CLAUDE_BIN", str(FAKE_CLAUDE))
    monkeypatch.setenv("FAKE_CLAUDE_DIR", str(root))
    return root


def _calls(root: Path, kind: str) -> list[str]:
    lines = (root / "calls.jsonl").read_text(encoding="utf-8").splitlines()
    return [c["prompt"] for c in map(json.loads, lines) if c["kind"] == kind]


def _type(monkeypatch: pytest.MonkeyPatch, *blocks: str) -> None:
    it: Iterator[str] = iter(blocks)
    monkeypatch.setattr(leetcode_repl, "read_block", lambda: next(it, None))


def _events(tmp_path: Path, slug: str) -> list[dict[str, Any]]:
    (path,) = (tmp_path / "sessions").glob(f"*-{slug}.jsonl")
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


def _coach(*texts: str) -> list[dict[str, str]]:
    return [{"result": t} for t in texts]


def _incomplete(*missing: str) -> dict[str, str]:
    return {"result": json.dumps({"verdict": "incomplete", "missing": list(missing)})}


def test_claude_path_req_first(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(local_session, "fetched_statement", lambda _p: STATEMENT)
    root = _script(
        tmp_path,
        monkeypatch,
        haiku=[
            _incomplete("self-inverse", "XOR"),
            _incomplete("self-inverse"),
            _incomplete("closed-form-total"),
        ],
        coach=_coach(
            "Restated. What feels unclear?\n<!-- rung:H0 -->",
            "What must the operation do?",
            "Closer. What is still open?",
            "Try the code?",
            "Run it on [3,0,1]?\n\n<!-- rung:H2 -->",
        ),
    )
    _type(monkeypatch, CODE, "req: find it", CODE, "req: v2", "req: v3", CODE, "quit")
    assert leetcode_repl.main(["missing-number"]) == 0
    out = capsys.readouterr().out
    assert "[code held back: write the requirement list first" in out
    assert "self-inverse: applying it twice with the same value undoes it" in out
    assert "[code held back: the req list is still incomplete" in out
    assert "accepted anyway" in out
    assert "XOR" not in out
    assert "<!--" not in out
    assert out.rstrip().endswith("Run it on [3,0,1]?")
    coach = _calls(root, "coach")
    assert coach[0] == "/leetcode missing-number"
    assert [c.split("\n")[0] for c in coach[1:4]] == [
        "req: find it",
        "req: v2",
        "req: v3",
    ]
    assert coach[4] == CODE  # the first code that reached the model: after 3 lists
    assert len(_calls(root, "haiku")) == 3
    events = _events(tmp_path, "missing-number")
    kinds = [e["event"] for e in events]
    assert kinds == ["rung", *["req", "req_check"] * 3, "code", "rung"]
    assert [e["verdict"] for e in events if e["event"] == "req_check"] == [
        "incomplete"
    ] * 3
    assert events[7]["req_incomplete"] is True
    assert events[-1]["rung"] == "H2"


def test_checker_down_fails_open_and_report_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(local_session, "fetched_statement", lambda _p: STATEMENT)
    _script(
        tmp_path,
        monkeypatch,
        haiku=[{"exit": 1, "stderr": "API Error: 500"}],
        coach=_coach("Open?", "List noted. Next?", "Run it?\n<!-- rung:H1 -->"),
    )
    _type(monkeypatch, "req: each value twice but one", CODE)
    assert leetcode_repl.main(["single-number"]) == 0
    assert "unverified" in capsys.readouterr().out
    events = _events(tmp_path, "single-number")
    assert [e["event"] for e in events] == ["req", "req_check", "code", "rung"]
    assert events[1]["verdict"] == "unverified"
    assert "req_incomplete" not in events[2]
    assert report.main([]) == 0
    rows = capsys.readouterr().out.splitlines()
    name = next(p.stem for p in (tmp_path / "sessions").glob("*.jsonl"))
    assert rows[1] == f"{name:<36}{'y':<17}{'H1':<10}{'n':<8}unverified"


@pytest.fixture
def ollama(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeOllama]:
    server = FakeOllama(
        checker=['{"verdict": "pass", "missing": []}'],
        coach=[
            "Restated. What feels unclear?",
            "Good list. What happens to a pair?",
            "Think XOR. What is a ^ a?",
            "What does a value do to itself under your rule?\n<!-- rung:H1 -->",
            "Yes, XOR. What is a ^ a?",
        ],
    )
    monkeypatch.setattr(local_backend, "OLLAMA_URL", server.url)
    yield server
    server.close()


def test_local_path_bounces_a_leak_but_not_a_typed_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    ollama: FakeOllama,
) -> None:
    monkeypatch.setattr(local_session, "fetch_statement", lambda *_a: STATEMENT)
    _script(tmp_path, monkeypatch, haiku=[{"exit": 1, "stderr": "usage limit reached"}])
    _type(monkeypatch, "req: pairs vanish, one survives", "no idea", "is it XOR?")
    assert leetcode_repl.main(["--local", "single-number"]) == 0
    out = capsys.readouterr().out
    assert "[req list accepted -- code is open]" in out
    assert "Think XOR" not in out
    assert "What does a value do to itself under your rule?" in out
    assert "Yes, XOR. What is a ^ a?" in out
    assert "<!--" not in out
    coach = [m for kind, m in ollama.seen if kind == "coach"]
    assert len(coach) == len(["open", "req", "leak", "rewrite", "typed"])
    assert "names XOR" in coach[3][-1]["content"]
    assert [k for k, _m in ollama.seen].count("checker") == 1
    events = _events(tmp_path, "single-number")
    assert [e["event"] for e in events] == ["req", "req_check", "rung"]
    assert events[1]["verdict"] == "pass"
