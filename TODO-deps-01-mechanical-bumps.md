# TODO — utils deps, session 1 of 2: the mechanical bumps

REMOVE ME AFTER FINISH

Running order: **this file first**, then `TODO-deps-02-major-upgrades.md`.
Session 2 does not depend on this one having run, but doing this first shrinks
the gate output to just the three majors, so a failure in session 2 is
unambiguous.

## Why this exists

`~/src/utils` has been red on the **dependency freshness** CI workflow since
2026-09-11 — every run on `main` since commit `001670f` has failed. It is not
a broken build: upstream moved and the exact pins did not. Measured
2026-09-12 with `./scripts/check_dependency_freshness.sh --all` (exit 1,
29 findings across 9 sub-packages).

This session does the **16 low-risk bumps only**. The three majors
(`very_good_analysis 11`, `vitest`/`@vitest/coverage-v8 5`, `pnpm 12`) are
session 2's job — do not touch them here, they need hand edits and a
separate blast-radius check.

`~/src/utils` is a shared monorepo: 8 Flutter apps consume its Dart packages
(`home_inventory`, `kuhylog`, `lyricanki`, `punchme`, `todo`, `untools`,
`restaurant-rater`, `epopeja_karta`) and 4 TS repos consume `@kuhyx/ts-core`
/ `@kuhyx/web-ui` (`europe-county-map`, `iron-and-anvil`,
`awesome-mcp-explorer`, `konbini-67`). Breaking a pin here breaks twelve
downstream repos, which is why every sub-package's suite must go green before
you commit.

## Read first

- `rules/dependency-freshness.instructions.md` — exact pins, stable only, the
  two allowlist classes, and **never `--no-verify`**.
- `dependency-freshness.allowlist.yaml` — top-of-file comment explains the two
  entry classes. It already holds ONE active entry (`npm:typescript` pinned
  6.0.3, `blocked_by: transitive:typescript-eslint@8.70.0`). **Leave it
  alone.** It is fleet-wide and correct; touching TypeScript is out of scope
  for both sessions.
- `scripts/run_subproject_tests.sh` — pre-commit runs hooks from the git root,
  but each sub-package's pytest config is relative to its own directory. This
  wrapper supplies the missing `cd`. Use it; do not hand-roll one.

## The 16 bumps

Exact, with the file and line the gate named:

| Ecosystem | Package | From → To | File |
|---|---|---|---|
| toolchain | node | 24.20.0 → 24.21.0 | `.github/workflows/ts-core-tests.yml:27` |
| toolchain | node | 24.20.0 → 24.21.0 | `.github/workflows/web-ui-tests.yml:27` |
| pypi | ruff | 0.16.5 → 0.16.7 | `crdt-sync/requirements.txt:11` |
| pypi | types-requests | 2.33.0.20260712 → 2.33.0.20260906 | `crdt-sync/requirements.txt:12` |
| pypi | ruff | 0.16.6 → 0.16.7 | `freedays/requirements.txt:10` |
| pypi | ruff | 0.16.5 → 0.16.7 | `gatelock/requirements.txt:10` |
| pub | test | 1.31.2 → 1.32.0 | `crdt_sync_dart/pubspec.yaml:17` |
| pub | flutter_secure_storage | 11.0.0 → 11.1.1 | `crdt_sync_flutter/pubspec.yaml:21` |
| npm | eslint | 10.9.1 → 10.10.0 | `ts_core/package.json:34` |
| npm | typescript-eslint | 8.68.0 → 8.70.0 | `ts_core/package.json:36` |
| npm | eslint | 10.9.1 → 10.10.0 | `web_ui/package.json:43` |
| npm | typescript-eslint | 8.68.0 → 8.70.0 | `web_ui/package.json:48` |
| npm | @testing-library/user-event | 14.6.6 → 14.6.7 | `web_ui/package.json:39` |
| npm | @types/react | 19.2.18 → 19.3.0 | `web_ui/package.json:40` |
| npm | @types/react-dom | 19.2.5 → 19.3.0 | `web_ui/package.json:41` |
| npm | react + react-dom | 19.2.8 → 19.3.0 | `web_ui/package.json:33,46` |

`react` and `react-dom` must move together — a split version pair is a
runtime error, not a lint finding.

Note `typescript-eslint 8.70.0` is already the version the allowlist entry
names as the TS-7 blocker. Bumping to it is expected and does **not**
invalidate that entry; do not edit the allowlist.

## Constraints you would otherwise rediscover painfully

- **pnpm only, never npm.** `@kuhyx/web-ui` is consumed as `&path:/web_ui`;
  npm cannot install a monorepo subdirectory and running it locks the repo
  into a broken state. Local pnpm is 11.26.0 (leave it — session 2 owns the
  pnpm 12 move), node is v24.18.0 via nvm. The node bumps above are **CI
  workflow pins only**; your local node does not need to match.
- **250-line cap** on every file, code and prose, enforced by
  `scripts/check_file_length.sh`.
- **No `# noqa`, no `type: ignore`, no per-file-ignores** without asking
  first, every time. Fix the underlying issue.
- **Never `--no-verify`.** If a hook fails, fix the failure.
- Heavy commands go through `~/.claude/scripts/capped.sh` (2 GiB / 10% CPU;
  raise per-invocation with `CAP_MEM=4G CAP_CPU_PCT=20`).
- Work on `main`; branch creation is blocked by a hook. Stage narrowly — no
  blanket `git add .`.

## Procedure

1. Apply the 16 edits above. Exact pins, no carets (the `very_good_analysis`
   carets stay as-is — they are session 2's).
2. Regenerate lockfiles where the ecosystem has one:
   - `crdt_sync_dart`, `crdt_sync_flutter`: `dart pub get` / `flutter pub get`
   - `ts_core`, `web_ui`: `pnpm install` (in each package directory)
   - Python requirements have no lockfile here.
3. Run each touched sub-package's suite and fix what breaks:
   - `scripts/run_subproject_tests.sh crdt-sync`
   - `scripts/run_subproject_tests.sh freedays`
   - `scripts/run_subproject_tests.sh gatelock`
   - `cd crdt_sync_dart && dart test`
   - `cd crdt_sync_flutter && flutter test`
   - `cd ts_core && pnpm lint && pnpm test`
   - `cd web_ui && pnpm lint && pnpm test`
   The React 19.2→19.3 bump is the one most likely to surface a test change;
   `eslint 10.10.0` may add a rule that fires. Fix the code, not the config.
4. `./scripts/check_dependency_freshness.sh --all` — expect exit 1 still, but
   **only** the three majors remaining (very_good_analysis ×4, vitest ×2,
   @vitest/coverage-v8 ×2, pnpm ×2). If anything else is listed, you missed a
   bump.
5. `pre-commit run --files <changed files>`.
6. Commit and push with `~/.claude/scripts/finish_auto.sh` (it runs the gate,
   stages narrowly, commits, pushes and watches CI with no LLM turns). Pass
   the changed files explicitly — it does not stage untracked files on its
   own.

## Exit condition

- `./scripts/check_dependency_freshness.sh --all` lists **only** the three
  major upgrades named above; every other finding is gone.
- Every sub-package suite listed in step 3 passes.
- Pushed to `main`, and the **dependency freshness** workflow is the only red
  CI check left on the repo (it stays red until session 2 lands — that is
  expected and is why session 2 exists).
- Delete this file as part of the final commit.
