# devstats: kuhy vs "the 100x programmer" article

Generated 2026-11-27 by `python -m devstats compare --write` (utils/devstats).
Article: https://veszelovszki.com/a/tpe/ (Cmdr, posted 2026-10-24).

- kuhy: every repo under ~/src, each piece of work once (worktrees, clones
  and rewritten copies folded in), commits on the default branch (local and
  origin tips), `--no-merges`, authored by kuhy's address (agent-made commits
  included). Committer date, local time.
- Net LoC = insertions − deletions of code paths. Docs/translations are left
  out of the headline like the article's; the "+docs" row adds them back.
- Cmdr's figures are per calendar day; the baseline (194) is per day with a
  push, so kuhy's per-active-day column divides by days with ≥1 counted commit.
- ×0.67 is the article's "Discount it by 33% to compensate for the AI bloat".

## LoC per calendar day vs Cmdr

| window | row | kuhy net LoC/day | ins/day | del/day | Cmdr LoC/day |
|---|---|---|---|---|---|
| 30 d | raw | 25,808 | 35,818 | 10,010 | 12,000 |
| 30 d | ×0.67 | 17,291 | 23,998 | 6,707 | 8,040 |
| 30 d | +docs | 26,220 | 37,070 | 10,850 | — |
| 90 d | raw | 19,533 | 24,524 | 4,992 | 9,700 |
| 90 d | ×0.67 | 13,087 | 16,431 | 3,344 | 6,499 |
| 90 d | +docs | 19,955 | 25,384 | 5,429 | — |
| 300 d ≈ lifetime (10 mo) | raw | 7,579 | 11,075 | 3,497 | 4,500 |
| 300 d ≈ lifetime (10 mo) | ×0.67 | 5,078 | 7,421 | 2,343 | 3,015 |
| 300 d ≈ lifetime (10 mo) | +docs | 7,923 | 11,795 | 3,871 | — |

## Per active day vs the 194 LoC/workday baseline

| window | active days | row | kuhy net LoC/active day | baseline LoC/workday | kuhy ÷ 194 | kuhy commits/active day | Cmdr commits/workday |
|---|---|---|---|---|---|---|---|
| 30 d | 24 | raw | 32,260 | 194 | 166.3× | 146 | 160 |
| 30 d | 24 | ×0.67 | 21,614 | 194 | 111.4× |  |  |
| 90 d | 77 | raw | 22,830 | 194 | 117.7× | 82 | — |
| 90 d | 77 | ×0.67 | 15,296 | 194 | 78.8× |  |  |
| 300 d ≈ lifetime (10 mo) | 181 | raw | 12,561 | 194 | 64.7× | 47 | 55 |
| 300 d ≈ lifetime (10 mo) | 181 | ×0.67 | 8,416 | 194 | 43.4× |  |  |

## Totals

| window | net code LoC | insertions | deletions | net +docs | excluded share | commits | tags | tags/week | Cmdr releases/week | repos with ≥1 tag |
|---|---|---|---|---|---|---|---|---|---|---|
| 30 d | 774,242 | 1,074,555 | 300,313 | 786,589 | 23% | 3,511 | 725 | 169.2 | ~2 | 26 |
| 90 d | 1,757,944 | 2,207,196 | 449,252 | 1,795,922 | 23% | 6,340 | 1226 | 95.4 | ~2 | 28 |
| 300 d ≈ lifetime (10 mo) | 2,273,591 | 3,322,648 | 1,049,057 | 2,376,996 | 33% | 8,562 | 1661 | 38.8 | ~2 | 31 |

## Exclude list (first match wins)

- excluded: `node_modules/`, `vendor/`, `third_party/`, `addons/`, `.venv/`, `.dart_tool/`, `dist/`, `build/`, `generated/`, `htmlcov/`, `coverage/`, `__snapshots__/`, `data/`, `assets/`, `fixtures/`, `*.lock`, `*.lockb`, `package-lock.json`, `npm-shrinkwrap.json`, `pnpm-lock.yaml`, `go.sum`, `*.g.dart`, `*.freezed.dart`, `*.mocks.dart`, `*.gr.dart`, `*.pb.go`, `*_pb2.py`, `*.min.js`, `*.min.css`, `*.map`, `coverage.xml`, `lcov.info`, `*.lcov`, `*.import`, `*.uid`, `*.snap`, `*.json`, `*.jsonl`, `*.ndjson`, `*.geojson`, `*.csv`, `*.tsv`, `*.txt`, `*.tcx`, `*.gpx`, `*.tres`, `*.svg`, `*.log`
- docs: `docs/`, `doc/`, `l10n/`, `locales/`, `i18n/`, `translations/`, `*.md`, `*.mdx`, `*.rst`, `*.adoc`, `*.arb`, `*.po`, `*.pot`, `LICENSE*`, `COPYING*`
- code: `godot_dev_tools/`, `package.json`, `tsconfig*.json`, `jsconfig.json`, `deno.json`, `requirements*.txt`, `CMakeLists.txt`
