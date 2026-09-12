# TODO — utils deps, session 2 of 2: the three major upgrades

REMOVE ME AFTER FINISH

Running order: `TODO-deps-01-mechanical-bumps.md` first, then **this file**.
If session 1 has not run, `./scripts/check_dependency_freshness.sh --all` will
list ~16 extra low-risk findings alongside the three below — ignore them here
and do session 1 first, or the gate can never reach exit 0.

## Why this exists

`~/src/utils` has been red on the **dependency freshness** CI workflow since
2026-09-11. Session 1 cleared the mechanical bumps. What is left are three
major-version moves, each with real breaking-change surface, measured
2026-09-12:

| Ecosystem | Package | From → To | Files |
|---|---|---|---|
| pub | very_good_analysis | `^10.3.0` → `11.0.0` | `crdt_sync_flutter/pubspec.yaml:37`, `design_system/pubspec.yaml:20`, `github_device_auth/pubspec.yaml:21`, `sync_settings_ui/pubspec.yaml:25` |
| npm | vitest | 4.1.11 → 5.0.0 | `ts_core/package.json:37`, `web_ui/package.json:49` |
| npm | @vitest/coverage-v8 | 4.1.11 → 5.0.0 | `ts_core/package.json:33`, `web_ui/package.json:42` |
| npm | pnpm | 11.24.0 → 12.4.1 | `ts_core/package.json:12`, `web_ui/package.json:12` |

`very_good_analysis` keeps a caret by an explicit carve-out in
`rules/dependency-freshness.instructions.md` (SDK-coupled packages may keep a
range), but **its range floor is still checked** — `^10.3.0` fails because the
floor is behind latest. `^11.0.0` is the target, not a bare `11.0.0`.

`~/src/utils` is shared: 8 Flutter apps consume its Dart packages
(`home_inventory`, `kuhylog`, `lyricanki`, `punchme`, `todo`, `untools`,
`restaurant-rater`, `epopeja_karta`) and 4 TS repos consume `@kuhyx/ts-core` /
`@kuhyx/web-ui` (`europe-county-map`, `iron-and-anvil`,
`awesome-mcp-explorer`, `konbini-67`). Every one of those repos pins its own
`very_good_analysis`, so lint changes here are a preview of work they will
each need — **do not fix them in this session**, just note what you hit.

## Read first

- `rules/dependency-freshness.instructions.md` — the Dart caret carve-out, the
  "range floor is still checked" rule, and **never `--no-verify`**.
- `dependency-freshness.allowlist.yaml` — ONE active entry (`npm:typescript`
  pinned 6.0.3, `blocked_by: transitive:typescript-eslint@8.70.0`, held
  fleet-wide). **Leave it alone.** TypeScript stays on 6.0.3 in both sessions.
- `design_system/analysis_options.yaml` — line 1 is
  `include: package:very_good_analysis/analysis_options.yaml`, so the lint set
  changes the moment the pin moves. The other three Dart packages follow the
  same pattern.

## What `very_good_analysis 11` actually changes

Recorded when the fleet first hit this (2026-09-11), so expect these three
and confirm against the package's own changelog before assuming the list is
complete:

- `async_return_with_no_await` — **needs hand edits.** Not auto-fixable.
- `unnecessary_type_name_in_constructor` — `dart fix --apply` handles it.
- `unnecessary_const_in_enum_constructor` — `dart fix --apply` handles it.

For scale: in `betting-sim` the two auto-fixable rules alone hit 164 sites.
The four utils packages are much smaller, but run `dart fix --dry-run` first
so you know what you are about to change.

## Constraints you would otherwise rediscover painfully

- **pnpm only, never npm.** `@kuhyx/web-ui` is consumed as `&path:/web_ui`;
  npm cannot install a monorepo subdirectory.
- **The pnpm 11 → 12 move is the riskiest item here.** Local pnpm is 11.26.0
  and `corepack` is present at `~/.nvm/versions/node/v24.18.0/bin/corepack`.
  The `packageManager` field carries a full `+sha512...` integrity hash —
  regenerate it, do not hand-edit the hash. A past "Failed to switch pnpm to
  vX" was a **stale shim in `$PNPM_HOME`**, not a pnpm bug; if you see it,
  look for a stale binary on `PATH` and never delete `PNPM_HOME` itself.
- **`vitest 5` is a major** — check its migration notes for config and
  coverage-provider changes before editing. `vitest` and
  `@vitest/coverage-v8` must move together; a version-skewed pair fails at
  coverage time, not at install time.
- **Coverage bars are not negotiable.** `scripts/check_coverage.sh` is the
  adjudicator; if vitest 5 reports coverage differently, fix the config, do
  not lower the bar.
- **No `# noqa` / `type: ignore` / per-file-ignores / lint disables** without
  asking first, every time. All 7 "unavoidable" disables in a past konbini-67
  session were reverted — exhaust refactors first.
- **250-line cap** on every file, enforced by `scripts/check_file_length.sh`.
- Heavy commands through `~/.claude/scripts/capped.sh`
  (`CAP_MEM=4G CAP_CPU_PCT=20` to raise).
- Work on `main`; branching is hook-blocked. Stage narrowly.

## Procedure

Do these as **three separate commits**, in this order — each is independently
revertable, and mixing them makes a CI failure impossible to attribute.

**A. `very_good_analysis` → `^11.0.0`** (4 pubspecs)
1. Bump all four, then `flutter pub get` / `dart pub get` in each.
2. `dart fix --dry-run` in each; review, then `dart fix --apply`.
3. Hand-fix every `async_return_with_no_await` finding.
4. `flutter analyze` / `dart analyze` clean in all four.
5. Suites — all four are Flutter packages, so `flutter test` in each (not
   `dart test`; only `crdt_sync_dart`, which this session does not touch, is
   pure Dart): `crdt_sync_flutter`, `design_system`, `github_device_auth`,
   `sync_settings_ui`.

**B. `vitest` + `@vitest/coverage-v8` → 5.0.0** (`ts_core`, `web_ui`)
1. Bump both packages in both manifests together. `pnpm install` in each.
2. `pnpm lint && pnpm test && pnpm coverage` in each.
3. If coverage reporting changed shape, fix the config so
   `scripts/check_coverage.sh` still adjudicates — do not relax the bar.

**C. `pnpm` → 12.4.1** (`ts_core`, `web_ui`)
1. `corepack use pnpm@12.4.1` in each package so the `packageManager` field
   and its integrity hash are regenerated, not hand-written.
2. `pnpm install` in each; commit the updated lockfiles.
3. `pnpm lint && pnpm test` in each.
4. Sanity-check one downstream consumer still resolves — e.g.
   `cd ~/src/konbini-67 && pnpm install` — but **do not commit** in that repo.

After all three: `./scripts/check_dependency_freshness.sh --all` → **exit 0**
(the one `npm:typescript` allowlist entry will print as an active exception;
that is expected and is not a failure).

Then `pre-commit run --files <changed>` and push each commit with
`~/.claude/scripts/finish_auto.sh`, passing changed files explicitly.

## Exit condition

- `./scripts/check_dependency_freshness.sh --all` exits **0**, with only the
  pre-existing `npm:typescript` exception reported.
- All four Dart packages analyze clean; `ts_core` and `web_ui` lint, test and
  meet their coverage bars.
- No new allowlist entries, no new lint suppressions, `typescript` still 6.0.3.
- The **dependency freshness** workflow is green on `main` — the whole point;
  it has been red since 2026-09-11.
- Delete this file (and `TODO-deps-01-*` if it is still present) in the final
  commit.

## If a transitive conflict blocks a bump

Stop and ask, per conflict. Exact pins plus latest-everywhere is provably
unsatisfiable when a dependency internally constrains a shared transitive.
**Never auto-add an allowlist entry** — that is the user's call, and a
discretionary entry needs an `expires` date capped at 90 days.
