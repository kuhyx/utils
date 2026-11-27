"""Repo discovery: one level under each root, worktrees folded into their repo."""

from __future__ import annotations

from pathlib import Path

from devstats.discover import discover

from .conftest import DAY, NOW, lines, run


def test_worktrees_count_once_under_the_main_repo(make_repo, tmp_path: Path) -> None:
    main = make_repo("signal-bot")
    main.commit({"a.py": lines(1)}, NOW - DAY)
    run(main.path, "worktree", "add", "-q", str(tmp_path / "src" / "sb-wt-a"), "-b", "wt-a")
    make_repo("other")
    (tmp_path / "src" / "not-a-repo").mkdir()
    (tmp_path / "src" / "file.txt").write_text("x")
    broken = tmp_path / "src" / "broken"
    broken.mkdir()
    (broken / ".git").write_text("gitdir: /nonexistent/worktree\n")
    repos, warnings = discover([tmp_path / "src"])
    assert [r.name for r in repos] == ["other", "signal-bot"]
    assert warnings == ["broken: not a readable git repo, skipped"]


def test_a_root_that_is_itself_a_repo_and_duplicate_roots(make_repo, tmp_path: Path) -> None:
    repo = make_repo("solo", root=tmp_path)
    repos, _ = discover([repo.path, repo.path, tmp_path / "missing"])
    assert [r.name for r in repos] == ["solo"]

