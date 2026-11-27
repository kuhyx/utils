"""Default-branch resolution from refs on disk (never fetches).

Only the LOCAL default branch is counted (kuhy's spec: "read local refs
only"). origin/HEAD only names the branch. When the `origin/` tracking ref is
newer, the caller warns: work landed with `git push origin HEAD:main` from a
worktree is then missing from the count until the checkout is pulled.
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
    """The default branch name, the local ref to log, and how stale it is."""

    branch: str | None
    log_refs: tuple[str, ...]
    behind_days: float | None


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
            behind = None
            if remote and local.sha != remote.sha and remote.ts > local.ts:
                behind = round((remote.ts - local.ts) / 86_400, 1)
            return DefaultRefs(branch, ("refs/heads/" + branch,), behind)
    return DefaultRefs(None, (), None)
