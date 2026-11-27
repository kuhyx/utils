"""Markdown tables: kuhy beside the article, plus the optional per-repo breakdown."""

from __future__ import annotations

from collections.abc import Sequence

from devstats import article as A
from devstats.aggregate import Window
from devstats.excludes import RULES

DASH = "—"


def _n(x: float) -> str:
    return f"{x:,.0f}"


def _table(head: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return out


def per_calendar_day(windows: Sequence[Window]) -> list[str]:
    """kuhy raw / ×0.67 / +docs LoC per calendar day beside Cmdr raw / ×0.67."""
    rows = []
    for w in windows:
        d, cmdr, label = w.days, A.CMDR_LOC_PER_DAY[w.days], A.LABELS[w.days]
        for row, k in (("raw", 1.0), ("×0.67", A.AI_DISCOUNT)):
            rows.append([label, row, _n(w.net * k / d), _n(w.code_ins * k / d),
                         _n(w.code_del * k / d), _n(cmdr * k)])
        rows.append([label, "+docs", _n(w.net_with_docs / d), _n((w.code_ins + w.docs_ins) / d),
                     _n((w.code_del + w.docs_del) / d), DASH])
    head = ("window", "row", "kuhy net LoC/day", "ins/day", "del/day", "Cmdr LoC/day")
    return _table(head, rows)


def per_active_day(windows: Sequence[Window]) -> list[str]:
    """kuhy per active day beside the 194 baseline, plus commits beside Cmdr's."""
    rows = []
    base = A.BASELINE_LOC_PER_WORKDAY
    for w in windows:
        active = max(w.active_days, 1)
        cmdr_commits = A.CMDR_COMMITS_PER_WORKDAY[w.days]
        for row, k in (("raw", 1.0), ("×0.67", A.AI_DISCOUNT)):
            per = w.net * k / active
            commits = [_n(w.commits / active), DASH if cmdr_commits is None else _n(cmdr_commits)]
            rows.append([A.LABELS[w.days], str(w.active_days), row, _n(per), str(base),
                         f"{per / base:.1f}×", *(commits if row == "raw" else ["", ""])])
    head = ("window", "active days", "row", "kuhy net LoC/active day", "baseline LoC/workday",
            "kuhy ÷ 194", "kuhy commits/active day", "Cmdr commits/workday")
    return _table(head, rows)


def totals(windows: Sequence[Window]) -> list[str]:
    """Raw totals, the share the exclude list removed, and tags."""
    rows = [
        [A.LABELS[w.days], _n(w.net), _n(w.code_ins), _n(w.code_del), _n(w.net_with_docs),
         f"{w.excluded_share:.0%}", _n(w.commits), str(w.tags), f"{w.tags / (w.days / 7):.1f}",
         f"~{A.RELEASES_PER_WEEK}", str(w.repos_with_tags)]
        for w in windows
    ]
    head = ("window", "net code LoC", "insertions", "deletions", "net +docs", "excluded share",
            "commits", "tags", "tags/week", "Cmdr releases/week", "repos with ≥1 tag")
    return _table(head, rows)


def report(windows: Sequence[Window]) -> str:
    """The comparison tables, as printed and as written to DOCS-comparison.md."""
    parts = ["## LoC per calendar day vs Cmdr", "", *per_calendar_day(windows), "",
             "## Per active day vs the 194 LoC/workday baseline", "", *per_active_day(windows), "",
             "## Totals", "", *totals(windows)]
    return "\n".join(parts) + "\n"


def by_repo(per_repo: Sequence[tuple[str, Sequence[Window]]], top: int) -> str:
    """Top-`top` repos by 300-day net code LoC (terminal only, never written)."""
    ranked = sorted(per_repo, key=lambda item: -item[1][-1].net)[:top]
    head = ("repo", *(f"net {A.LABELS[d].split(' ≈')[0]}" for d in A.WINDOWS), "commits 300 d")
    rows = [[name, *(_n(w.net) for w in ws), _n(ws[-1].commits)] for name, ws in ranked]
    return "\n".join(["## Top repos", "", *_table(head, rows)]) + "\n"


def exclude_list() -> str:
    """The exclude list grouped by bucket, for the doc."""
    lines = []
    for bucket in ("excluded", "docs", "code"):
        pats = ", ".join(f"`{p}`" for b, p in RULES if b == bucket)
        lines.append(f"- {bucket}: {pats}")
    return "\n".join(lines) + "\n"


def document(windows: Sequence[Window], date: str) -> str:
    """Full DOCS-comparison.md body: aggregates only, no repo names."""
    intro = f"""# devstats: kuhy vs "the 100x programmer" article

Generated {date} by `python -m devstats compare --write` (utils/devstats).
Article: {A.URL} (Cmdr, posted 2026-10-24).

- kuhy: every repo under ~/src, each piece of work once (worktrees, clones
  and rewritten copies folded in), commits on the default branch (local and
  origin tips), `--no-merges`, authored by kuhy's address (agent-made commits
  included). Committer date, local time.
- Net LoC = insertions − deletions of code paths. Docs/translations are left
  out of the headline like the article's; the "+docs" row adds them back.
- Cmdr's figures are per calendar day; the baseline (194) is per day with a
  push, so kuhy's per-active-day column divides by days with ≥1 counted commit.
- ×0.67 is the article's "Discount it by 33% to compensate for the AI bloat".

"""
    return intro + report(windows) + "\n## Exclude list (first match wins)\n\n" + exclude_list()
