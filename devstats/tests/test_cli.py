"""End to end: `python -m devstats compare` over a scratch ~/src."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from devstats.cli import main

from .conftest import DAY, NOW, lines, run


@pytest.fixture
def src(make_repo, tmp_path: Path) -> Path:
    """signal-bot + a worktree, a master-only repo, a collaborator, a stale ref."""
    bot = make_repo("signal-bot")
    bot.commit({"bot.py": lines(100), "README.md": lines(40), "pnpm-lock.yaml": lines(500)}, NOW - DAY)
    bot.commit({"bot.py": None}, NOW - 50 * DAY + 1)  # dates out of order on purpose: kept by --since
    bot.commit({"x.py": lines(10)}, NOW - 2 * DAY, email="ppolgon@gmail.com")
    bot.tag("v1", NOW - DAY, annotated=True)
    bot.commit({"pushed.py": lines(3)}, NOW - DAY)  # pushed from a worktree: only origin has it
    run(bot.path, "update-ref", "refs/remotes/origin/main", "HEAD")
    run(bot.path, "update-ref", "refs/heads/main", "HEAD~1")  # local main behind origin
    run(bot.path, "worktree", "add", "-q", str(tmp_path / "src" / "sb-wt-a"), "-b", "wt")
    old = make_repo("old", branch="master")
    old.commit({"o.py": lines(20)}, NOW - 200 * DAY)
    nob = make_repo("nobranch", branch="dev")
    nob.commit({"n.py": lines(7)}, NOW - DAY)
    return tmp_path / "src"


def compare(*args: str, doc: Path) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    rc = main(["compare", *args], now=NOW, out=out, err=err, doc_path=doc)
    return rc, out.getvalue(), err.getvalue()


def test_compare_prints_all_windows_and_article_figures(src: Path, tmp_path: Path) -> None:
    doc = tmp_path / "DOCS-comparison.md"
    rc, out, err = compare("--root", str(src), doc=doc)
    assert rc == 0
    for needle in ("30 d", "90 d", "300 d ≈ lifetime (10 mo)", "12,000", "9,700", "4,500", "×0.67", "194",
                   "160", "55", "+docs", "excluded", "tags/week", "repos with ≥1 tag", "÷ 194"):
        assert needle in out, needle
    assert "signal-bot (main): default ref is 1.0 days behind its upstream tracking ref" in err
    assert "nobranch: no main/master/origin HEAD branch, skipped" in err
    assert not doc.exists()
    assert "signal-bot" not in out


def test_by_repo_folds_worktrees_and_write_has_no_repo_names(src: Path, tmp_path: Path) -> None:
    doc = tmp_path / "DOCS-comparison.md"
    rc, out, _ = compare("--root", str(src), "--by-repo", "--write", doc=doc)
    assert rc == 0
    assert "signal-bot" in out
    assert "sb-wt" not in out
    text = doc.read_text()
    assert "Generated 2026-11-18" in text
    assert "pnpm-lock.yaml" in text  # the exclude list is printed
    for name in ("signal-bot", "sb-wt", "old", "nobranch"):
        assert f"| {name}" not in text


def test_a_local_clone_changes_nothing_but_the_repo_list(src: Path, tmp_path: Path) -> None:
    doc = tmp_path / "d.md"
    _, before, _ = compare("--root", str(src), doc=doc)
    run(src, "clone", "-q", "signal-bot", "bot-clone")
    _, after, _ = compare("--root", str(src), doc=doc)
    assert before == after


def test_email_flag_adds_the_collaborator(src: Path, tmp_path: Path) -> None:
    doc = tmp_path / "d.md"
    _, base, _ = compare("--root", str(src), "--by-repo", "1", doc=doc)
    _, more, _ = compare("--root", str(src), "--by-repo", "1", "--email", "PPolgon@gmail.com", doc=doc)
    assert base != more


def test_default_root_is_home_src(src: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    rc, out, _ = compare(doc=tmp_path / "d.md")
    assert rc == 0
    assert "| 30 d" in out


def test_no_repos_is_an_error(tmp_path: Path) -> None:
    rc, _, err = compare("--root", str(tmp_path / "empty"), doc=tmp_path / "d.md")
    assert rc == 2
    assert "no git repos" in err


def test_compare_leaves_the_walked_repos_untouched(src: Path, tmp_path: Path) -> None:
    before = {p: run(p, "for-each-ref") + run(p, "status", "--porcelain") for p in src.iterdir()}
    compare("--root", str(src), doc=tmp_path / "d.md")
    after = {p: run(p, "for-each-ref") + run(p, "status", "--porcelain") for p in src.iterdir()}
    assert before == after
    assert not (src / "signal-bot" / ".git" / "FETCH_HEAD").exists()


def test_module_entry_point(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import runpy

    monkeypatch.setattr("sys.argv", ["devstats", "compare", "--help"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("devstats", run_name="__main__")
    assert exc.value.code == 0
    assert "--by-repo" in capsys.readouterr().out
