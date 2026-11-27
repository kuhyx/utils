"""Figures from https://veszelovszki.com/a/tpe/ (post dated 2026-10-24).

Cmdr's LoC/day are per calendar day, weekends included, and exclude
"generated code, libraries, docs, etc." (docs and translations are a separate
"+800k"). The windows are the article's: last 30 days ~12,000, last 90 days
~9,700, lifetime (~10 months) 4,500. The 194 baseline is Sourcegraph LoC per
day "when I pushed code", i.e. per active day. Commits: ~160/workday in
October, ~55/workday lifetime, no 90-day figure. Releases: ~2/week.
"Discount it by 33%" (x0.67) applies to Cmdr's rates, not to the baseline.
"""

from __future__ import annotations

URL = "https://veszelovszki.com/a/tpe/"
WINDOWS: tuple[int, ...] = (30, 90, 300)
LABELS = {30: "30 d", 90: "90 d", 300: "300 d ≈ lifetime (10 mo)"}
CMDR_LOC_PER_DAY = {30: 12_000, 90: 9_700, 300: 4_500}
CMDR_COMMITS_PER_WORKDAY: dict[int, int | None] = {30: 160, 90: None, 300: 55}
BASELINE_LOC_PER_WORKDAY = 194
RELEASES_PER_WEEK = 2
AI_DISCOUNT = 0.67
