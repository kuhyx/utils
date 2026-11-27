"""Parsing `git log --numstat -z` and reading one ref set from a real repo."""

from __future__ import annotations

from devstats.numstat import FileChange, parse_log, read_commits

from .conftest import DAY, ME, NOW, lines


def test_parse_empty_input() -> None:
    assert parse_log(b"") == []


def test_parse_commit_without_files_then_rename_first() -> None:
    raw = (
        b"\x1eaaa\x1f100\x1fMe@X.com\x1f90\x1fFix: a\x1fb\x00\n"
        b"\x1ebbb\x1f200\x1fme@x.com\x1f190\x1fsecond\x00\n"
        b"3\t1\t\x00old.py\x00new.py\x00-\t-\tlogo.png\x002\t0\tb.md\x00"
    )
    first, second = parse_log(raw)
    assert first.sha == "aaa"
    assert first.ts == 100
    assert first.email == "me@x.com"
    assert first.files == ()
    assert (first.author_ts, first.subject) == (90, "Fix: a\x1fb")
    assert second.identity == ("me@x.com", 190, "second")
    assert second.churn == 6
    assert second.files == (
        FileChange("new.py", 3, 1, binary=False),
        FileChange("logo.png", 0, 0, binary=True),
        FileChange("b.md", 2, 0, binary=False),
    )


def test_read_commits_skips_merges_and_old_commits(make_repo) -> None:
    repo = make_repo("r")
    repo.commit({"old.py": lines(50)}, NOW - 400 * DAY)
    repo.commit({"a.py": lines(10)}, NOW - 5 * DAY)
    base = repo.path
    from .conftest import run

    run(base, "checkout", "-q", "-b", "side")
    repo.commit({"b.py": lines(4)}, NOW - 4 * DAY)
    run(base, "checkout", "-q", "main")
    repo.commit({"c.py": lines(2)}, NOW - 3 * DAY)
    run(
        base,
        "merge",
        "-q",
        "--no-ff",
        "-m",
        "m",
        "side",
        env={"GIT_COMMITTER_DATE": f"@{NOW - 2 * DAY} +0000", "GIT_AUTHOR_DATE": f"@{NOW - 2 * DAY} +0000"},
    )
    repo.rename("a.py", "z.py", NOW - DAY, extra="tail\n")
    got = read_commits(base, ["refs/heads/main"], NOW - 300 * DAY)
    files = sorted(f.path for c in got for f in c.files)
    assert files == ["a.py", "b.py", "c.py", "z.py"]
    assert all(c.email == ME for c in got)
    rename = next(c for c in got if any(f.path == "z.py" for f in c.files))
    assert rename.files == (FileChange("z.py", 1, 0, binary=False),)


def test_read_commits_dedups_commits_reachable_from_two_refs(make_repo) -> None:
    repo = make_repo("r")
    repo.commit({"a.py": lines(3)}, NOW - DAY)
    from .conftest import run

    run(repo.path, "update-ref", "refs/remotes/origin/main", "HEAD")
    got = read_commits(repo.path, ["refs/heads/main", "refs/remotes/origin/main"], NOW - 30 * DAY)
    assert len(got) == 1


def test_binary_and_pure_rename_from_a_real_repo(make_repo) -> None:
    repo = make_repo("r")
    repo.commit({"logo.png": b"\x00\x01\x02", "a.py": lines(5)}, NOW - 2 * DAY)
    repo.rename("a.py", "b.py", NOW - DAY)
    got = read_commits(repo.path, ["refs/heads/main"], NOW - 30 * DAY)
    assert got[0].files == (FileChange("b.py", 0, 0, binary=False),)
    assert FileChange("logo.png", 0, 0, binary=True) in got[1].files
