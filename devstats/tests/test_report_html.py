"""The static report page: chart above tables, cells identical to the terminal's."""

from __future__ import annotations

import re
from html import unescape

from devstats.aggregate import Window
from devstats.report_html import CMDR, KUHY, chart, page
from devstats.render import report


def window(days: int, net: int) -> Window:
    return Window(days=days, code_ins=max(net, 0), code_del=max(-net, 0), docs_ins=5, docs_del=1,
                  excluded_lines=10, all_lines=100, active_days=3, commits=7, tags=2, repos_with_tags=1)


WINDOWS = [window(30, 3000), window(90, 900), window(300, 30)]


def md_cells(text: str) -> list[str]:
    """Body cells of every markdown table (header and separator rows skipped)."""
    cells = []
    for block in text.split("## ")[1:]:
        rows = [ln for ln in block.splitlines() if ln.startswith("|")][2:]
        cells += [c.strip() for r in rows for c in r.strip("|").split("|")]
    return cells


def test_page_cells_match_the_terminal_tables() -> None:
    html = page(WINDOWS, "2026-11-27")
    tds = [unescape(c) for c in re.findall(r"<td>(.*?)</td>", html)]
    assert tds == md_cells(report(WINDOWS))
    assert "<title>devstats 2026-11-27</title>" in html


def test_chart_comes_before_the_tables_and_names_both_series() -> None:
    html = page(WINDOWS, "d")
    assert html.index('class="chart"') < html.index("<table")
    assert "</i>kuhy</span>" in html and "</i>Cmdr</span>" in html
    assert html.count(f'background:{KUHY}" title=') == 6
    assert html.count(f'background:{CMDR}" title=') == 6
    assert 'title="kuhy 30 d · raw: 100"' in html
    assert 'title="Cmdr 300 d · ×0.67: 3,015"' in html
    assert 'style="width:82.0%;background:#398FC0" title="Cmdr 30 d · raw: 12,000"' in html


def test_zero_or_negative_net_draws_no_bar_but_keeps_the_value() -> None:
    html = chart([window(30, 0), window(90, -900), window(300, 0)])
    assert f"background:{KUHY}\" title=" not in html
    assert "<span>-10</span>" in html  # -900 / 90 d, printed as is
    assert html.count(f'background:{CMDR}" title=') == 6
