"""Window totals: buckets, active days, excluded share, tags."""

from __future__ import annotations

from devstats.aggregate import RepoData, dedup, window_totals
from devstats.numstat import Commit, FileChange

from .conftest import DAY, NOW


def commit(days_ago: float, *files: FileChange) -> Commit:
    ts = int(NOW - days_ago * DAY)
    return Commit(sha=f"s{days_ago}", ts=ts, email="me", files=files, author_ts=ts, subject=f"c{days_ago}")


def fc(path: str, ins: int, dels: int, binary: bool = False) -> FileChange:
    return FileChange(path, ins, dels, binary=binary)


def test_window_totals_split_buckets_and_windows() -> None:
    repo = RepoData(
        name="r",
        commits=(
            commit(1, fc("a.py", 100, 20), fc("README.md", 10, 0), fc("uv.lock", 50, 20)),
            commit(1.2, fc("b.py", 5, 5), fc("logo.png", 0, 0, binary=True)),
            commit(40, fc("c.py", 30, 0)),
            commit(400, fc("d.py", 999, 0)),
        ),
        tags=(("t1", NOW - 2 * DAY), ("t2", NOW - 50 * DAY), ("t3", NOW - 500 * DAY), ("t4", NOW + DAY)),
    )
    empty = RepoData(name="e", commits=(), tags=())
    w30 = window_totals([repo, empty], 30, NOW)
    assert (w30.code_ins, w30.code_del, w30.net) == (105, 25, 80)
    assert w30.net_with_docs == 90
    assert w30.commits == 2
    assert w30.active_days == 1
    assert w30.tags == 1
    assert w30.repos_with_tags == 1
    assert w30.excluded_share == 70 / 210
    w90 = window_totals([repo], 90, NOW)
    assert (w90.net, w90.commits, w90.active_days, w90.tags) == (110, 3, 2, 2)


def test_empty_window_has_zero_share() -> None:
    w = window_totals([], 30, NOW)
    assert (w.net, w.excluded_share, w.active_days) == (0, 0.0, 0)


def test_dedup_keeps_the_larger_copy_of_rewritten_work() -> None:
    small = Commit("x1", 10, "me", (fc("a.py", 1, 0),), author_ts=5, subject="s")
    big = Commit("x2", 20, "me", (fc("a.py", 9, 0), fc("b.py", 1, 0)), author_ts=5, subject="s")
    other = Commit("x3", 30, "me", (fc("c.py", 1, 0),), author_ts=6, subject="s")
    tie = Commit("x4", 40, "me", (fc("d.py", 1, 0),), author_ts=7, subject="t")
    a = RepoData("archive", (small, tie), (("t", 1), ("u", 2)))
    b = RepoData("main", (big, other, tie), (("t", 1),))
    got = dedup([a, b])
    assert [c.sha for c in got[0].commits] == ["x4"]
    assert [c.sha for c in got[1].commits] == ["x2", "x3"]
    assert (got[0].tags, got[1].tags) == ((("t", 1), ("u", 2)), ())
