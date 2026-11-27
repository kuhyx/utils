"""Per-window totals over every repo's commits and tags."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from devstats.excludes import classify
from devstats.numstat import Commit

DAY = 86_400


@dataclass(frozen=True)
class RepoData:
    """Counted commits (already filtered to the chosen emails) and (sha, ts) tags of one repo."""

    name: str
    commits: tuple[Commit, ...]
    tags: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class Window:
    """Totals for the last `days` days."""

    days: int
    code_ins: int
    code_del: int
    docs_ins: int
    docs_del: int
    excluded_lines: int
    all_lines: int
    commits: int
    active_days: int
    tags: int
    repos_with_tags: int

    @property
    def net(self) -> int:
        """Headline: code insertions minus deletions (docs and excluded paths left out)."""
        return self.code_ins - self.code_del

    @property
    def net_with_docs(self) -> int:
        """Net including markdown/translations ("+docs")."""
        return self.net + self.docs_ins - self.docs_del

    @property
    def excluded_share(self) -> float:
        """Share of all changed lines (ins+del) the exclude list dropped."""
        return self.excluded_lines / self.all_lines if self.all_lines else 0.0


def dedup(repos: Sequence[RepoData]) -> list[RepoData]:
    """Count each piece of work once across repos.

    A filter-repo split (testsAndMisc -> testsAndMisc-archive) or a fork
    (kuhytrack -> leisure-watch) carries the same commits, rewritten or not.
    Copies share email + author time + subject; the copy with the larger diff
    is kept (the earlier repo on a tie), the others are dropped. A tag object
    seen in an earlier repo (a clone) is dropped too.
    """
    best: dict[tuple[str, int, str], tuple[int, Commit]] = {}
    for i, repo in enumerate(repos):
        for c in repo.commits:
            seen = best.get(c.identity)
            if seen is None or c.churn > seen[1].churn:
                best[c.identity] = (i, c)
    keep = {(i, c.sha) for i, c in best.values()}
    seen_tags: set[str] = set()
    out = []
    for i, repo in enumerate(repos):
        tags = tuple(t for t in repo.tags if t[0] not in seen_tags)
        seen_tags.update(sha for sha, _ in repo.tags)
        out.append(replace(repo, commits=tuple(c for c in repo.commits if (i, c.sha) in keep),
                           tags=tags))
    return out


def window_totals(repos: Sequence[RepoData], days: int, now: float) -> Window:
    """Aggregate `repos` over the `days` days before `now`."""
    cutoff = now - days * DAY
    sums = {"code": [0, 0], "docs": [0, 0], "excluded": [0, 0]}
    commits = 0
    dates: set[object] = set()
    tags = repos_with_tags = 0
    for repo in repos:
        for c in repo.commits:
            if c.ts < cutoff:
                continue
            commits += 1
            dates.add(datetime.fromtimestamp(c.ts).date())
            for f in c.files:
                if not f.binary:
                    bucket = sums[classify(f.path)]
                    bucket[0] += f.ins
                    bucket[1] += f.dels
        n = sum(1 for _, t in repo.tags if cutoff <= t <= now)
        tags += n
        repos_with_tags += n > 0
    excluded = sum(sums["excluded"])
    return Window(
        days=days,
        code_ins=sums["code"][0],
        code_del=sums["code"][1],
        docs_ins=sums["docs"][0],
        docs_del=sums["docs"][1],
        excluded_lines=excluded,
        all_lines=excluded + sum(sums["code"]) + sum(sums["docs"]),
        commits=commits,
        active_days=len(dates),
        tags=tags,
        repos_with_tags=repos_with_tags,
    )
