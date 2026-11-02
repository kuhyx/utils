"""Branches that a healthy sandbox never reaches: crashes, bad results, no bwrap."""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path
import subprocess
from typing import TYPE_CHECKING

import pytest

from code_runner import Example, Limits, RunnerError, run
from code_runner._examples import parse_examples
from code_runner._languages import JAVASCRIPT, PYTHON, get_language
from code_runner._run import Box, _read_result
from code_runner._sandbox import BoxResult, bwrap_argv, check_sandbox
from code_runner._starter import parse_starter

if TYPE_CHECKING:
    from collections.abc import Iterator

STARTER = "def f(a):\n"
EXAMPLE = Example(1, {"a": 1}, 1)


@pytest.fixture(autouse=True)
def _fresh_sandbox_check() -> Iterator[None]:
    check_sandbox.cache_clear()
    yield
    check_sandbox.cache_clear()


def _fake(result: BoxResult, files: dict[str, str] | None = None) -> Box:
    def box(
        command: list[str],
        scratch: Path,
        limits: Limits,
        memory: int,
        binds: tuple[str, ...],
    ) -> BoxResult:
        for name, text in (files or {}).items():
            (scratch / name).write_text(text)
        return result

    return box


def _box(**kw: object) -> BoxResult:
    fields = {
        "returncode": 0,
        "timed_out": False,
        "stdout": "",
        "stderr": "",
        "elapsed_ms": 7.0,
    }
    return BoxResult(**(fields | kw))


def _run(box: Box) -> object:
    return run("python3", "", STARTER, [EXAMPLE], box=box)[0]


def test_crash_without_result_names_the_exit_code() -> None:
    result = _run(_fake(_box(returncode=139)))
    assert (result.ok, result.actual, result.error, result.ms) == (
        False,
        None,
        "Crashed (exit 139)",
        7.0,
    )


def test_out_of_memory_crash_is_named() -> None:
    stderr = "FATAL ERROR: Reached heap limit Allocation failed - JavaScript heap out of memory"
    assert (
        _run(_fake(_box(returncode=134, stderr=stderr))).error == "MemoryLimitExceeded"
    )


def test_timeout_wins_over_a_result_file() -> None:
    files = {"result.json": '{"ok": true, "value": 1}'}
    result = _run(_fake(_box(timed_out=True, elapsed_ms=1000.0), files))
    assert (result.error, result.ms) == ("TimeLimitExceeded", 1000.0)


def test_result_file_variants() -> None:
    good = _run(
        _fake(_box(stdout="hi"), {"result.json": '{"ok": true, "value": 1, "ms": 2.5}'})
    )
    assert (good.ok, good.ms, good.stdout) == (True, 2.5, "hi")
    no_ms = _run(_fake(_box(), {"result.json": '{"ok": true, "value": 1}'}))
    assert no_ms.ms == 7.0
    failed = _run(_fake(_box(), {"result.json": '{"ok": false}'}))
    assert failed.error == "Error"
    named = _run(
        _fake(_box(), {"result.json": '{"ok": false, "error": "KeyError: x"}'})
    )
    assert named.error == "KeyError: x"


def test_hostile_result_files_cost_one_example_not_the_run() -> None:
    hostile = {
        "bomb": "[" * 200_000,
        "deep": '{"ok": true, "value": ' + "[" * 5000 + "]" * 5000 + "}",
        "huge_ms": '{"ok": true, "value": 1, "ms": 1' + "0" * 400 + "}",
        "bool_ms": '{"ok": true, "value": 1, "ms": true}',
        "long_error": '{"ok": false, "error": "' + "x" * 5000 + '"}',
    }
    results = {
        name: _run(_fake(_box(), {"result.json": text}))
        for name, text in hostile.items()
    }
    assert results["bomb"].error == "Crashed (exit 0)"
    assert results["deep"].error == "Crashed (exit 0)"
    assert (results["huge_ms"].ok, results["huge_ms"].ms) == (True, 7.0)
    assert results["bool_ms"].ms == 7.0
    assert len(results["long_error"].error) == 200


def test_too_deep_expected_or_actual_is_that_examples_error() -> None:
    deep: object = 1
    for _ in range(100):
        deep = [deep]
    files = {"result.json": '{"ok": true, "value": 1}'}
    cases = [Example(1, {"a": 1}, deep), EXAMPLE]
    results = run("python3", "", STARTER, cases, box=_fake(_box(), files))
    assert (results[0].ok, results[0].actual) == (False, None)
    assert results[0].error == "InvalidResult: TooDeepError"
    assert results[1].ok is True  # the run went on


def test_recursion_in_compare_is_that_examples_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*args: object) -> bool:
        raise RecursionError

    monkeypatch.setattr("code_runner._run.matches", boom)
    files = {"result.json": '{"ok": true, "value": 1}'}
    result = _run(_fake(_box(), files))
    assert result.error == "InvalidResult: RecursionError"


def test_unreadable_result_files_are_a_crash(tmp_path: Path) -> None:
    secret = tmp_path / "secret"
    secret.write_text('{"ok": true, "value": "stolen"}')
    (tmp_path / "result.json").symlink_to(secret)
    assert _read_result(tmp_path) is None
    (tmp_path / "result.json").unlink()
    os.mkfifo(tmp_path / "result.json")
    assert _read_result(tmp_path) is None
    (tmp_path / "result.json").unlink()
    for text in ("not json", "[1]", '{"no": "ok"}'):
        (tmp_path / "result.json").write_text(text)
        assert _read_result(tmp_path) is None
    assert _read_result(tmp_path / "missing") is None


def test_binary_resolution(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ghost = dataclasses.replace(
        PYTHON, binary_default="/nope", program="no-such-program-xyz"
    )
    monkeypatch.delenv(ghost.binary_env, raising=False)
    with pytest.raises(RunnerError, match="no-such-program-xyz not found"):
        ghost.resolve()
    tool = tmp_path / "bin" / "python3"
    tool.parent.mkdir()
    tool.write_text("#!/bin/sh\n")
    monkeypatch.setenv(ghost.binary_env, str(tool))
    assert ghost.resolve() == tool
    assert ghost.ro_binds(tool) == (str(tool.parent.parent),)
    assert PYTHON.ro_binds(Path("/usr/bin/python3")) == ()
    assert get_language("TS").name == "typescript"


def _has(argv: list[str], seq: list[str]) -> bool:
    return any(argv[i : i + len(seq)] == seq for i in range(len(argv)))


def test_argv_binds_links_and_limits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("code_runner._sandbox._ROOT_LINKS", ("usr", "no-such-root-dir"))
    argv = bwrap_argv(["prog"], tmp_path, Limits(timeout_s=1.2), 123, ("/opt/x",))
    assert _has(argv, ["--ro-bind", "/usr", "/usr"])
    assert _has(argv, ["--ro-bind", "/opt/x", "/opt/x"])
    assert _has(argv, ["--bind", str(tmp_path), "/work"])
    assert "--share-net" not in argv
    assert {"--unshare-all", "--die-with-parent", "--clearenv", "--remount-ro"} <= set(
        argv
    )
    assert "--as=123" in argv
    assert "--cpu=3" in argv
    assert argv[-1] == "prog"


def test_sandbox_preflight_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("code_runner._sandbox.PRLIMIT", "/no/such/prlimit")
    with pytest.raises(RunnerError, match="prlimit"):
        check_sandbox()
    monkeypatch.undo()

    def missing(*args: object, **kwargs: object) -> None:
        message = "bwrap"
        raise FileNotFoundError(message)

    monkeypatch.setattr(subprocess, "run", missing)
    with pytest.raises(RunnerError, match="cannot start"):
        check_sandbox()

    def refused(*args: object, **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(args, 1, b"", b"bwrap: No permissions\n")

    monkeypatch.setattr(subprocess, "run", refused)
    with pytest.raises(RunnerError, match="No permissions"):
        check_sandbox()


def test_statement_and_starter_edge_cases() -> None:
    escaped = parse_examples('**Input:** s = "a\\"b,c", t = 1\n**Output:** "x"\n')
    assert escaped[0].args == {"s": 'a"b,c', "t": 1}
    assert parse_starter("python3", "def f(a, b").params == ("a", "b")
    skipped = "class S {\n  if (x) {\n  solve(a) {\n  }\n}\n"
    assert parse_starter("javascript", skipped).name == "solve"


def test_typescript_class_entry_is_exported(tmp_path: Path) -> None:
    entry = parse_starter(
        "typescript", "class Solution {\n  solve(a: number): number {\n  }\n}\n"
    )
    get_language("typescript").prepare(tmp_path, "class Solution {}", entry, [1])
    assert "__entry: Solution" in (tmp_path / "solution.cts").read_text()
    JAVASCRIPT.prepare(tmp_path, "x", entry, [1])
    assert (tmp_path / "solution.js").read_text() == "x"
