"""Tables of kuhy beside the article, plus the optional per-repo breakdown.

The `*_rows` builders return (head, rows) of plain cell strings; the markdown
here and the HTML page in `devstats.html` both render those, so the page and
the terminal always show the same numbers.
"""

from __future__ import annotations

from collections.abc import Sequence

from devstats import article as A
from devstats.aggregate import Window
from devstats.excludes import RULES

DASH = "—"
Table = tuple[tuple[str, ...], list[list[str]]]


def num(x: float) -> str:
    """Whole number with thousands separators."""
    return f"{x:,.0f}"


def _table(head: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return out


def per_calendar_day(windows: Sequence[Window]) -> Table:
    """kuhy raw / ×0.67 / +docs LoC per calendar day beside Cmdr raw / ×0.67."""
    rows = []
    for w in windows:
        d, cmdr, label = w.days, A.CMDR_LOC_PER_DAY[w.days], A.LABELS[w.days]
        for row, k in (("raw", 1.0), ("×0.67", A.AI_DISCOUNT)):
            rows.append([label, row, num(w.net * k / d), num(w.code_ins * k / d),
                         num(w.code_del * k / d), num(cmdr * k)])
        rows.append([label, "+docs", num(w.net_with_docs / d), num((w.code_ins + w.docs_ins) / d),
                     num((w.code_del + w.docs_del) / d), DASH])
    head = ("window", "row", "kuhy net LoC/day", "ins/day", "del/day", "Cmdr LoC/day")
    return head, rows


def per_active_day(windows: Sequence[Window]) -> Table:
    """kuhy per active day beside the 194 baseline, plus commits beside Cmdr's."""
    rows = []
    base = A.BASELINE_LOC_PER_WORKDAY
    for w in windows:
        active = max(w.active_days, 1)
        cmdr_commits = A.CMDR_COMMITS_PER_WORKDAY[w.days]
        for row, k in (("raw", 1.0), ("×0.67", A.AI_DISCOUNT)):
            per = w.net * k / active
            commits = [num(w.commits / active), DASH if cmdr_commits is None else num(cmdr_commits)]
            rows.append([A.LABELS[w.days], str(w.active_days), row, num(per), str(base),
                         f"{per / base:.1f}×", *(commits if row == "raw" else ["", ""])])
    head = ("window", "active days", "row", "kuhy net LoC/active day", "baseline LoC/workday",
            "kuhy ÷ 194", "kuhy commits/active day", "Cmdr commits/workday")
    return head, rows


def totals(windows: Sequence[Window]) -> Table:
    """Raw totals, the share the exclude list removed, and tags."""
    rows = [
        [A.LABELS[w.days], num(w.net), num(w.code_ins), num(w.code_del), num(w.net_with_docs),
         f"{w.excluded_share:.0%}", num(w.commits), str(w.tags), f"{w.tags / (w.days / 7):.1f}",
         f"~{A.RELEASES_PER_WEEK}", str(w.repos_with_tags)]
        for w in windows
    ]
    head = ("window", "net code LoC", "insertions", "deletions", "net +docs", "excluded share",
            "commits", "tags", "tags/week", "Cmdr releases/week", "repos with ≥1 tag")
    return head, rows


def sections(windows: Sequence[Window]) -> list[tuple[str, Table]]:
    """(title, table) of each comparison table, in print order."""
    return [("LoC per calendar day vs Cmdr", per_calendar_day(windows)),
            ("Per active day vs the 194 LoC/workday baseline", per_active_day(windows)),
            ("Totals", totals(windows))]


def report(windows: Sequence[Window]) -> str:
    """The comparison tables, as printed and as written to DOCS-comparison.md."""
    blocks = ["\n".join([f"## {title}", "", *_table(head, rows)])
              for title, (head, rows) in sections(windows)]
    return "\n\n".join(blocks) + "\n"


def by_repo(per_repo: Sequence[tuple[str, Sequence[Window]]], top: int) -> str:
    """Top-`top` repos by 300-day net code LoC (terminal only, never written)."""
    ranked = sorted(per_repo, key=lambda item: -item[1][-1].net)[:top]
    head = ("repo", *(f"net {A.LABELS[d].split(' ≈')[0]}" for d in A.WINDOWS), "commits 300 d")
    rows = [[name, *(num(w.net) for w in ws), num(ws[-1].commits)] for name, ws in ranked]
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
  and rewritten copies folded in), commits on the local default branch plus
  its `origin/` tracking ref as last fetched (each SHA once; nothing fetched
  or pulled), `--no-merges`, authored by kuhy's address (agent-made commits
  included). Committer date, local time.
- Net LoC = insertions − deletions of code paths. Docs/translations are left
  out of the headline like the article's; the "+docs" row adds them back.
- Cmdr's figures are per calendar day; the baseline (194) is per day with a
  push, so kuhy's per-active-day column divides by days with ≥1 counted commit.
- ×0.67 is the article's "Discount it by 33% to compensate for the AI bloat".

"""
    return intro + report(windows) + "\n## Exclude list (first match wins)\n\n" + exclude_list()
