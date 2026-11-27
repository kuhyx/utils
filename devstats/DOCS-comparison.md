# devstats: kuhy vs "the 100x programmer" article

Generated 2026-11-27 by `python -m devstats compare --write` (utils/devstats).
Article: https://veszelovszki.com/a/tpe/ (Cmdr, posted 2026-10-24).

- kuhy: every repo under ~/src, each piece of work once (worktrees, clones
  and rewritten copies folded in), commits on the local default branch
  (nothing read from origin/, nothing fetched), `--no-merges`, authored by
  kuhy's address (agent-made commits included). Committer date, local time.
- Net LoC = insertions − deletions of code paths. Docs/translations are left
  out of the headline like the article's; the "+docs" row adds them back.
- Cmdr's figures are per calendar day; the baseline (194) is per day with a
  push, so kuhy's per-active-day column divides by days with ≥1 counted commit.
- ×0.67 is the article's "Discount it by 33% to compensate for the AI bloat".

## LoC per calendar day vs Cmdr

| window | row | kuhy net LoC/day | ins/day | del/day | Cmdr LoC/day |
|---|---|---|---|---|---|
| 30 d | raw | 24,639 | 34,238 | 9,599 | 12,000 |
| 30 d | ×0.67 | 16,508 | 22,939 | 6,431 | 8,040 |
| 30 d | +docs | 25,006 | 35,426 | 10,420 | — |
| 90 d | raw | 19,191 | 24,082 | 4,890 | 9,700 |
| 90 d | ×0.67 | 12,858 | 16,135 | 3,277 | 6,499 |
| 90 d | +docs | 19,598 | 24,920 | 5,322 | — |
| 300 d ≈ lifetime (10 mo) | raw | 7,568 | 11,044 | 3,475 | 4,500 |
| 300 d ≈ lifetime (10 mo) | ×0.67 | 5,071 | 7,399 | 2,328 | 3,015 |
| 300 d ≈ lifetime (10 mo) | +docs | 7,909 | 11,756 | 3,848 | — |

## Per active day vs the 194 LoC/workday baseline

| window | active days | row | kuhy net LoC/active day | baseline LoC/workday | kuhy ÷ 194 | kuhy commits/active day | Cmdr commits/workday |
|---|---|---|---|---|---|---|---|
| 30 d | 24 | raw | 30,799 | 194 | 158.8× | 141 | 160 |
| 30 d | 24 | ×0.67 | 20,635 | 194 | 106.4× |  |  |
| 90 d | 77 | raw | 22,431 | 194 | 115.6× | 81 | — |
| 90 d | 77 | ×0.67 | 15,029 | 194 | 77.5× |  |  |
| 300 d ≈ lifetime (10 mo) | 181 | raw | 12,544 | 194 | 64.7× | 47 | 55 |
| 300 d ≈ lifetime (10 mo) | 181 | ×0.67 | 8,405 | 194 | 43.3× |  |  |

## Totals

| window | net code LoC | insertions | deletions | net +docs | excluded share | commits | tags | tags/week | Cmdr releases/week | repos with ≥1 tag |
|---|---|---|---|---|---|---|---|---|---|---|
| 30 d | 739,179 | 1,027,137 | 287,958 | 750,168 | 23% | 3,391 | 726 | 169.4 | ~2 | 26 |
| 90 d | 1,727,195 | 2,167,336 | 440,141 | 1,763,815 | 23% | 6,219 | 1227 | 95.4 | ~2 | 28 |
| 300 d ≈ lifetime (10 mo) | 2,270,522 | 3,313,061 | 1,042,539 | 2,372,569 | 32% | 8,442 | 1662 | 38.8 | ~2 | 31 |

## Exclude list (first match wins)

- excluded: `node_modules/`, `vendor/`, `third_party/`, `addons/`, `.venv/`, `.dart_tool/`, `dist/`, `build/`, `generated/`, `htmlcov/`, `coverage/`, `__snapshots__/`, `*.lock`, `*.lockb`, `package-lock.json`, `npm-shrinkwrap.json`, `pnpm-lock.yaml`, `go.sum`, `*.g.dart`, `*.freezed.dart`, `*.mocks.dart`, `*.gr.dart`, `*.pb.go`, `*_pb2.py`, `*.min.js`, `*.min.css`, `*.map`, `coverage.xml`, `lcov.info`, `*.lcov`, `*.import`, `*.uid`, `*.snap`, `data/`, `assets/`, `fixtures/`, `*.json`, `*.jsonl`, `*.ndjson`, `*.geojson`, `*.csv`, `*.tsv`, `*.txt`, `*.tcx`, `*.gpx`, `*.tres`, `*.svg`, `*.log`
- docs: `docs/`, `doc/`, `l10n/`, `locales/`, `i18n/`, `translations/`, `*.md`, `*.mdx`, `*.rst`, `*.adoc`, `*.arb`, `*.po`, `*.pot`, `LICENSE*`, `COPYING*`
- code: `godot_dev_tools/`, `package.json`, `tsconfig*.json`, `jsconfig.json`, `deno.json`, `requirements*.txt`, `CMakeLists.txt`, `*.py`, `*.dart`, `*.ts`, `*.tsx`, `*.js`, `*.jsx`, `*.mjs`, `*.gd`, `*.go`, `*.kt`, `*.kts`, `*.java`, `*.sh`, `*.c`, `*.h`, `*.cpp`, `*.rs`, `*.lua`
