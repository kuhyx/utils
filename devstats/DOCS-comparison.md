# devstats: kuhy vs "the 100x programmer" article

Generated 2026-11-27 by `python -m devstats compare --write` (utils/devstats).
Article: https://veszelovszki.com/a/tpe/ (Cmdr, posted 2026-10-24).

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

## LoC per calendar day vs Cmdr

| window | row | kuhy net LoC/day | ins/day | del/day | Cmdr LoC/day |
|---|---|---|---|---|---|
| 30 d | raw | 26,280 | 36,348 | 10,068 | 12,000 |
| 30 d | ×0.67 | 17,608 | 24,353 | 6,745 | 8,040 |
| 30 d | +docs | 26,716 | 37,628 | 10,912 | — |
| 90 d | raw | 19,733 | 24,779 | 5,046 | 9,700 |
| 90 d | ×0.67 | 13,221 | 16,602 | 3,381 | 6,499 |
| 90 d | +docs | 20,163 | 25,647 | 5,484 | — |
| 300 d ≈ lifetime (10 mo) | raw | 7,733 | 11,255 | 3,522 | 4,500 |
| 300 d ≈ lifetime (10 mo) | ×0.67 | 5,181 | 7,541 | 2,360 | 3,015 |
| 300 d ≈ lifetime (10 mo) | +docs | 8,080 | 11,976 | 3,897 | — |

## Per active day vs the 194 LoC/workday baseline

| window | active days | row | kuhy net LoC/active day | baseline LoC/workday | kuhy ÷ 194 | kuhy commits/active day | Cmdr commits/workday |
|---|---|---|---|---|---|---|---|
| 30 d | 24 | raw | 32,851 | 194 | 169.3× | 148 | 160 |
| 30 d | 24 | ×0.67 | 22,010 | 194 | 113.5× |  |  |
| 90 d | 77 | raw | 23,065 | 194 | 118.9× | 83 | — |
| 90 d | 77 | ×0.67 | 15,453 | 194 | 79.7× |  |  |
| 300 d ≈ lifetime (10 mo) | 181 | raw | 12,816 | 194 | 66.1× | 48 | 55 |
| 300 d ≈ lifetime (10 mo) | 181 | ×0.67 | 8,587 | 194 | 44.3× |  |  |

## Totals

| window | net code LoC | insertions | deletions | net +docs | excluded share | commits | tags | tags/week | Cmdr releases/week | repos with ≥1 tag |
|---|---|---|---|---|---|---|---|---|---|---|
| 30 d | 788,415 | 1,090,449 | 302,034 | 801,473 | 23% | 3,556 | 732 | 170.8 | ~2 | 26 |
| 90 d | 1,775,992 | 2,230,132 | 454,140 | 1,814,652 | 23% | 6,383 | 1233 | 95.9 | ~2 | 28 |
| 300 d ≈ lifetime (10 mo) | 2,319,758 | 3,376,373 | 1,056,615 | 2,423,874 | 32% | 8,607 | 1668 | 38.9 | ~2 | 31 |

## Exclude list (first match wins)

- excluded: `node_modules/`, `vendor/`, `third_party/`, `addons/`, `.venv/`, `.dart_tool/`, `dist/`, `build/`, `generated/`, `htmlcov/`, `coverage/`, `__snapshots__/`, `*.lock`, `*.lockb`, `package-lock.json`, `npm-shrinkwrap.json`, `pnpm-lock.yaml`, `go.sum`, `*.g.dart`, `*.freezed.dart`, `*.mocks.dart`, `*.gr.dart`, `*.pb.go`, `*_pb2.py`, `*.min.js`, `*.min.css`, `*.map`, `coverage.xml`, `lcov.info`, `*.lcov`, `*.import`, `*.uid`, `*.snap`, `data/`, `assets/`, `fixtures/`, `*.json`, `*.jsonl`, `*.ndjson`, `*.geojson`, `*.csv`, `*.tsv`, `*.txt`, `*.tcx`, `*.gpx`, `*.tres`, `*.svg`, `*.log`
- docs: `docs/`, `doc/`, `l10n/`, `locales/`, `i18n/`, `translations/`, `*.md`, `*.mdx`, `*.rst`, `*.adoc`, `*.arb`, `*.po`, `*.pot`, `LICENSE*`, `COPYING*`
- code: `godot_dev_tools/`, `package.json`, `tsconfig*.json`, `jsconfig.json`, `deno.json`, `requirements*.txt`, `CMakeLists.txt`, `*.py`, `*.dart`, `*.ts`, `*.tsx`, `*.js`, `*.jsx`, `*.mjs`, `*.gd`, `*.go`, `*.kt`, `*.kts`, `*.java`, `*.sh`, `*.c`, `*.h`, `*.cpp`, `*.rs`, `*.lua`
