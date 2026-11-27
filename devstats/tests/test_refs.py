"""Default-branch resolution and the stale-local-ref warning."""

from __future__ import annotations

from devstats.refs import Ref, list_refs, resolve, tag_times

from .conftest import DAY, NOW, lines, run


def ref(ts: int, sha: str = "s", symref: str = "") -> Ref:
    return Ref(sha=sha, ts=ts, symref=symref, created=ts)


def test_origin_head_names_the_branch_and_both_tips_are_logged() -> None:
    refs = {
        "refs/remotes/origin/HEAD": ref(0, symref="refs/remotes/origin/trunk"),
        "refs/remotes/origin/trunk": ref(NOW, sha="o"),
        "refs/heads/trunk": ref(NOW - 2 * DAY - DAY // 2, sha="l"),
        "refs/heads/main": ref(NOW),
    }
    got = resolve(refs)
    assert got.branch == "trunk"
    assert got.log_refs == ("refs/heads/trunk",)
    assert got.behind_days == 2.5


def test_falls_back_to_main_then_master_without_origin() -> None:
    assert resolve({"refs/heads/main": ref(1)}).log_refs == ("refs/heads/main",)
    got = resolve({"refs/heads/master": ref(1), "refs/heads/dev": ref(2)})
    assert got.branch == "master"
    assert got.behind_days is None


def test_origin_only_branch_is_not_counted() -> None:
    got = resolve({"refs/remotes/origin/HEAD": ref(0, symref="refs/remotes/origin/main"),
                   "refs/remotes/origin/main": ref(1)})
    assert (got.branch, got.log_refs) == (None, ())


def test_no_default_branch() -> None:
    got = resolve({"refs/heads/dev": ref(1)})
    assert got.branch is None
    assert got.log_refs == ()


def test_local_ahead_or_equal_is_not_behind() -> None:
    same = {"refs/heads/main": ref(5, sha="a"), "refs/remotes/origin/main": ref(5, sha="a")}
    ahead = {"refs/heads/main": ref(9, sha="a"), "refs/remotes/origin/main": ref(5, sha="b")}
    assert resolve(same).behind_days is None
    assert resolve(ahead).behind_days is None


def test_list_refs_reads_branches_remotes_and_tags(make_repo) -> None:
    repo = make_repo("r")
    repo.commit({"a.py": lines(1)}, NOW - 10 * DAY)
    repo.tag("v1", NOW - 9 * DAY, annotated=True)
    repo.tag("light", NOW - 8 * DAY)
    run(repo.path, "update-ref", "refs/remotes/origin/main", "HEAD")
    run(repo.path, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    refs = list_refs(repo.path)
    assert refs["refs/remotes/origin/HEAD"].symref == "refs/remotes/origin/main"
    assert refs["refs/heads/main"].ts == NOW - 10 * DAY
    # annotated: tagger date; lightweight: the commit's date
    assert sorted(ts for _, ts in tag_times(refs)) == [NOW - 10 * DAY, NOW - 9 * DAY]
    assert refs["refs/tags/light"].sha in dict(tag_times(refs))
