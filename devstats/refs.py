"""Default-branch resolution from refs on disk (never fetches, never pulls).

The local default branch is logged together with its `origin/` tracking ref
when the two tips differ. Work landed with `git push origin HEAD:main` from a
worktree sits only on the tracking ref until the checkout is pulled, and kuhy's
live checkouts (tutor, todo) must not be pulled by a stats run. `git log` walks
the union, so each SHA counts once and a diverged repo counts both sides.
origin/HEAD only names the branch; a branch that exists only on origin/ is not
counted (no local checkout of that work).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from devstats.gitcmd import git

_FORMAT = "%(refname)%09%(symref)%09%(objectname)%09%(committerdate:unix)%09%(creatordate:unix)"
_ORIGIN = "refs/remotes/origin/"


@dataclass(frozen=True)
class Ref:
    """One ref: tip sha, tip committer ts (0 for tag objects), symref target, creator ts."""

    sha: str
    ts: int
    symref: str
    created: int


@dataclass(frozen=True)
class DefaultRefs:
    """The default branch name and the refs whose union is logged."""

    branch: str | None
    log_refs: tuple[str, ...]


def list_refs(repo: Path) -> dict[str, Ref]:
    """Every local branch, origin remote-tracking ref and tag, in one git call."""
    out = git(repo, "for-each-ref", f"--format={_FORMAT}", "refs/heads", "refs/remotes/origin",
              "refs/tags").decode(errors="replace")
    refs: dict[str, Ref] = {}
    for line in out.splitlines():
        name, symref, sha, ts, created = line.split("\t")
        refs[name] = Ref(sha=sha, ts=int(ts or 0), symref=symref, created=int(created or 0))
    return refs


def tag_times(refs: dict[str, Ref]) -> list[tuple[str, int]]:
    """(object sha, creator ts) of every tag: tagger date, or the commit date if lightweight."""
    return [(r.sha, r.created) for name, r in refs.items() if name.startswith("refs/tags/")]


def resolve(refs: dict[str, Ref]) -> DefaultRefs:
    """origin/HEAD's branch, else main, else master: the first that exists locally."""
    head = refs.get(_ORIGIN + "HEAD")
    candidates = [head.symref.removeprefix(_ORIGIN)] if head and head.symref else []
    for branch in (*candidates, "main", "master"):
        local, remote = refs.get("refs/heads/" + branch), refs.get(_ORIGIN + branch)
        if local:
            tracking = (_ORIGIN + branch,) if remote and remote.sha != local.sha else ()
            return DefaultRefs(branch, ("refs/heads/" + branch, *tracking))
    return DefaultRefs(None, ())
