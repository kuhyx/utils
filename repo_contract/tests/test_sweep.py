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
    assert main([], roots=[tmp_path], out=out) == 0
    assert "1 repos, 0 pass, 1 fail" in capsys.readouterr().out
    assert out.is_file()


@pytest.fixture
def no_walk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect HOME and make any walk fail loudly; return the default out path."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))

    def boom(roots: list[Path]) -> list[Path]:
        raise AssertionError(f"walked {roots}")

    monkeypatch.setattr("repo_contract.sweep.find_repos", boom)
    return tmp_path / "default" / "SWEEP.md"


def test_help_exits_0_without_walk_or_write(
    no_walk: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--help"], out=no_walk)
    assert exc.value.code == 0
    text = capsys.readouterr().out
    assert "~/src" in text and "SWEEP.md" in text
    assert "--dry-run" in text and "--out" in text
    assert not no_walk.exists()


def test_unknown_arg_exits_2_without_walk_or_write(
    no_walk: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--bogus"], out=no_walk)
    assert exc.value.code == 2
    assert "usage:" in capsys.readouterr().err
    assert not no_walk.exists()


def test_dry_run_prints_report_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    make_repo(tmp_path / "src" / "r")
    out = tmp_path / "default" / "SWEEP.md"
    assert main(["--dry-run"], roots=[tmp_path / "src"], out=out) == 0
    cap = capsys.readouterr()
    assert cap.out.startswith("# Repo contract sweep")
    assert "| r | FAIL |" in cap.out
    assert "1 repos, 0 pass, 1 fail" in cap.err and "dry run" in cap.err
    assert not out.exists() and not out.parent.exists()


def test_out_flag_writes_given_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    make_repo(tmp_path / "src" / "r")
    default = tmp_path / "default" / "SWEEP.md"
    given = tmp_path / "x" / "SWEEP.md"
    assert main(["--out", str(given)], roots=[tmp_path / "src"], out=default) == 0
    assert given.read_text(encoding="utf-8").startswith("# Repo contract sweep")
    assert not default.exists()
    assert f"-> {given}" in capsys.readouterr().out


def test_cli_help_runs_as_script(tmp_path: Path) -> None:
    script = Path(__file__).resolve().parents[1] / "sweep.py"
    env = {"HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}
    proc = subprocess.run(
        ["python3", str(script), "--help"],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == 0 and "--dry-run" in proc.stdout
    assert not (tmp_path / "data").exists()
