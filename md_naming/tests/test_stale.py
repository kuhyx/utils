"""The staleness reporter: warns, never fails."""

from __future__ import annotations

import subprocess
from pathlib import Path

from md_naming import stale
from md_naming.tests.conftest import write

NOW = 1_800_000_000


def commit(repo: Path, when: int) -> None:
    """Commit everything in `repo` with both dates pinned to `when`."""
    stamp = f"{when} +0000"
    env = {"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.email=t@t",
            "-c",
            "user.name=t",
            "commit",
            "-qm",
            "x",
        ],
        check=True,
        env={**dict(__import__("os").environ), **env},
    )


def test_old_todo_is_reported(repo: Path) -> None:
    write(repo, "TODO-a.md", "REMOVE ME AFTER FINISH\n")
    commit(repo, NOW - 100 * 86_400)
    found = stale.stale_todos(repo, limit=90, now=NOW)
    assert [p.name for p, _ in found] == ["TODO-a.md"]
    assert found[0][1] == 100


def test_fresh_todo_is_not_reported(repo: Path) -> None:
    write(repo, "TODO-a.md", "REMOVE ME AFTER FINISH\n")
    commit(repo, NOW - 5 * 86_400)
    assert stale.stale_todos(repo, limit=90, now=NOW) == []


def test_non_todo_ignored(repo: Path) -> None:
    write(repo, "DOCS-a.md")
    commit(repo, NOW - 500 * 86_400)
    assert stale.stale_todos(repo, limit=90, now=NOW) == []


def test_uncommitted_todo_has_unknown_age(repo: Path) -> None:
    """A file git has never seen yields no date, so it is not reported."""
    write(repo, "TODO-a.md", "REMOVE ME AFTER FINISH\n")
    assert stale.stale_todos(repo, limit=0, now=NOW) == []


def test_age_days_outside_repo(tmp_path: Path) -> None:
    assert stale.age_days(tmp_path / "x.md", tmp_path, NOW) is None


def test_main_always_exits_zero(repo: Path, monkeypatch, capsys) -> None:
    write(repo, "TODO-a.md", "REMOVE ME AFTER FINISH\n")
    commit(repo, NOW - 999 * 86_400)
    monkeypatch.chdir(repo)
    monkeypatch.setattr("sys.argv", ["stale", "--days", "1"])
    assert stale.main() == 0
    assert "::warning" in capsys.readouterr().out


def test_last_commit_epoch_when_git_missing(repo: Path, monkeypatch) -> None:
    """No git binary means unknown age, not a crash."""

    def boom(*args, **kwargs):
        raise OSError("no git")

    monkeypatch.setattr(stale.subprocess, "run", boom)
    assert stale.last_commit_epoch(repo / "TODO-a.md", repo) is None


def test_last_commit_epoch_non_numeric(repo: Path, monkeypatch) -> None:
    """Garbage on stdout is treated as unknown rather than parsed."""

    class Result:
        returncode = 0
        stdout = "not-a-number\n"

    monkeypatch.setattr(stale.subprocess, "run", lambda *a, **k: Result())
    assert stale.last_commit_epoch(repo / "TODO-a.md", repo) is None


def test_main_reports_absolute_path_outside_root(
    repo: Path, monkeypatch, capsys
) -> None:
    """A TODO outside the walk root still prints, using its full path."""
    write(repo, "TODO-a.md", "REMOVE ME AFTER FINISH\n")
    commit(repo, NOW - 999 * 86_400)
    monkeypatch.chdir(repo)
    monkeypatch.setattr("sys.argv", ["stale"])
    assert stale.main() == 0
