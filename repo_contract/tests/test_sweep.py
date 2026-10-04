"""Sweep report."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from repo_contract.sweep import Result, find_repos, main, render, run_one

from .conftest import good_repo, write


def make_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def test_find_repos_skips_dot_and_non_repos(tmp_path: Path) -> None:
    make_repo(tmp_path / "a")
    make_repo(tmp_path / ".hidden")
    (tmp_path / "plain").mkdir()
    assert find_repos([tmp_path, tmp_path / "missing"]) == [tmp_path / "a"]


def test_run_one_and_render(tmp_path: Path) -> None:
    ok = good_repo(make_repo(tmp_path / "ok"))
    bad = make_repo(tmp_path / "bad")
    write(bad, "CLAUDE.md").write_bytes(b"\xff\xfe")
    results = [run_one(ok), run_one(bad), Result("x", tmp_path, [], ["a|b"])]
    assert [r.passed for r in results] == [True, False, False]
    text = render(results)
    assert "3 repos: 1 pass, 2 fail." in text
    assert "| python | 1 | 0 |" in text and "| none | 2 | 2 |" in text
    assert "a/b" in text and "unreadable" in text


def test_main_writes_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_repo(tmp_path / "r")
    out = tmp_path / "out" / "SWEEP.md"
    assert main(roots=[tmp_path], out=out) == 0
    assert "1 repos, 0 pass, 1 fail" in capsys.readouterr().out
    assert out.is_file()
