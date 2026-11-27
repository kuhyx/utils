"""Find repos one level under each root and fold worktrees into their repo.

Worktrees (e.g. the sb-wt-* signal-bot checkouts) share one git common dir
with their main repo, so deduplicating on it counts every repo once, named
after the common dir's parent whichever checkout was walked first.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from devstats.gitcmd import GitError, git


@dataclass(frozen=True)
class Repo:
    """One repository: display name and a checkout path to run git in."""

    name: str
    path: Path


def _candidates(root: Path) -> list[Path]:
    """The root itself if it is a checkout, else its direct children that are."""
    if (root / ".git").exists():
        return [root]
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.is_dir() and (p / ".git").exists())


def discover(roots: Sequence[Path]) -> tuple[list[Repo], list[str]]:
    """Repos under `roots`, one per git common dir, plus warnings for broken ones."""
    seen: dict[Path, Repo] = {}
    warnings: list[str] = []
    for root in roots:
        for path in _candidates(root):
            try:
                out = git(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
            except GitError:
                warnings.append(f"{path.name}: not a readable git repo, skipped")
                continue
            common = Path(out.decode().strip())
            seen.setdefault(common, Repo(name=common.parent.name, path=path))
    return sorted(seen.values(), key=lambda r: r.name), warnings
