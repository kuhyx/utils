"""Static HTML report: a kuhy-vs-Cmdr bar chart above the three terminal tables.

One self-contained file (inline CSS, no script, no network), so it stays
readable after the run ends and opens from `file://`. Table cells come from
`render.sections`, the same builders the terminal prints, so the numbers match.
Colours are the unified-design-system tokens: kuhy `cat-3`, Cmdr `cat-2` (the
pair that passes the dataviz CVD check; `cat-1`/`cat-2` fall to dE 6.9 protan).
"""

from __future__ import annotations

from collections.abc import Sequence
from html import escape

from devstats import article as A
from devstats.aggregate import Window
from devstats.render import num, sections

KUHY, CMDR = "#C85A32", "#398FC0"
BAR_SHARE = 82  # % of the track the longest bar fills; the rest holds its value label

CSS = """
:root{--bg:#F6F4F3;--card:#FCFBFB;--line:#E0DAD7;--text:#211D1B;--muted:#70625B;color-scheme:light dark}
@media (prefers-color-scheme:dark){:root{--bg:#211D1B;--card:#2B2624;--line:#463E3A;--text:#ECEAE9;
--muted:#AAA09A}}
html{font-size:16px}@media (min-width:2400px){html{font-size:22px}}
body{margin:0;background:var(--bg);color:var(--text);font:1rem/1.5 system-ui,sans-serif}
main{max-width:100rem;margin:0 auto;padding:1.5rem 1rem 3rem;box-sizing:border-box}
h2{font-size:1.125rem;font-weight:600;margin:2rem 0 .75rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:1rem}
.scroll{overflow-x:auto}
.legend{display:flex;gap:1.5rem;margin:0 0 .75rem}.legend span{display:flex;align-items:center;gap:.4rem}
.sw{width:.75rem;height:.75rem;border-radius:2px}
.chart{display:grid;grid-template-columns:max-content 1fr;gap:1rem .75rem;align-items:center}
.lab{color:var(--muted);text-align:right;font-size:.875rem}
.pair{display:grid;gap:2px;border-left:1px solid var(--line)}
.track{display:flex;align-items:center;gap:.4rem;font-size:.875rem;font-variant-numeric:tabular-nums}
.bar{height:1rem;border-radius:0 4px 4px 0}
table{border-collapse:collapse;font-variant-numeric:tabular-nums;white-space:nowrap}
th,td{padding:.375rem .75rem;border-bottom:1px solid var(--line);text-align:right}
th{color:var(--muted);font-weight:600}th:nth-child(-n+2),td:nth-child(-n+2){text-align:left}
tr:last-child td{border-bottom:0}
"""


def _bars(windows: Sequence[Window]) -> list[tuple[str, float, float]]:
    """(row label, kuhy net LoC/day, Cmdr LoC/day) for each window, raw then x0.67."""
    out = []
    for w in windows:
        label = A.LABELS[w.days].split(" ≈")[0]
        for row, k in (("raw", 1.0), ("×0.67", A.AI_DISCOUNT)):
            out.append((f"{label} · {row}", w.net * k / w.days, A.CMDR_LOC_PER_DAY[w.days] * k))
    return out


def _track(who: str, label: str, value: float, peak: float, colour: str) -> str:
    """One bar (none when value <= 0) plus its value, with a hover tooltip."""
    share = max(value, 0) / peak * BAR_SHARE
    bar = (f'<i class="bar" style="width:{share:.1f}%;background:{colour}" '
           f'title="{escape(f"{who} {label}: {num(value)}")}"></i>') if share > 0 else ""
    return f'<div class="track">{bar}<span>{num(value)}</span></div>'


def chart(windows: Sequence[Window]) -> str:
    """Horizontal paired bars, kuhy above Cmdr, LoC per calendar day; HTML so text scales."""
    bars = _bars(windows)
    peak = max([1.0, *(max(k, c) for _, k, c in bars)])
    legend = "".join(f'<span><i class="sw" style="background:{c}"></i>{who}</span>'
                     for who, c in (("kuhy", KUHY), ("Cmdr", CMDR)))
    rows = "".join(f'<div class="lab">{escape(label)}</div><div class="pair">'
                   f"{_track('kuhy', label, k, peak, KUHY)}{_track('Cmdr', label, c, peak, CMDR)}</div>"
                   for label, k, c in bars)
    return (f'<div class="legend">{legend}</div>'
            f'<div class="chart" role="img" aria-label="kuhy vs Cmdr LoC per day">{rows}</div>')


def _html_table(head: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    cells = "".join(f"<th>{escape(h)}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{escape(c)}</td>" for c in r) + "</tr>" for r in rows)
    return f'<div class="card scroll"><table><thead><tr>{cells}</tr></thead><tbody>{body}</tbody></table></div>'


def page(windows: Sequence[Window], date: str) -> str:
    """The whole report page."""
    tables = "".join(f"<h2>{escape(title)}</h2>{_html_table(head, rows)}"
                     for title, (head, rows) in sections(windows))
    return (f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>devstats {escape(date)}</title><style>{CSS}</style></head><body><main>"
            f'<div class="card">{chart(windows)}</div>{tables}</main></body></html>\n')
