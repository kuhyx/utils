# repo_contract

Shared gate: every repo tells an agent how to run and test it, so nobody has to
explore. Enforced like the other shared gates (real gate in `~/src/utils`, a
thin shim per repo, pre-commit + CI).

## The contract

`CLAUDE.md` (or `AGENTS.md` that `CLAUDE.md` symlinks to) has a `## Commands`
section with one line per key, exactly `- <key>: \`<command>\``:

```markdown
## Commands

- run: `<command>` | n/a: library
- test: `<full suite>`
- test-changed: `scripts/test_changed.sh`
- lint: `<command>`
- coverage: `<command writing a report>`
- coverage-gaps: `coverage-gaps <report>`
```

Rules (all machine-checked):

1. All six keys present, once each. A value is a backticked command or
   `n/a: <reason>` / `n/a (<reason>)`. A bare `n/a` fails: n/a carries a reason.
2. `test-changed` invokes an existing, executable `scripts/test_changed.sh`-style
   script that runs only tests related to files changed vs HEAD, falls back to
   the full suite when it cannot map, and prints failures plus a one-line
   summary only.
3. `coverage-gaps` runs the shared lister `coverage-gaps <report>`
   (`~/src/utils/coverage_gaps`).
4. `test`, `test-changed`, `lint`, `coverage` are quiet: no `-v`/`--verbose`/
   expanded reporter, in the command or in the script's runner lines.
5. No placeholders (`<FILL IN>`, `TODO`, `...`).
6. If `test` is n/a, then `test-changed`, `coverage`, `coverage-gaps` are n/a
   too, and the repo must contain no tests (bounded scan).

## Use

```bash
python3 ~/src/utils/repo_contract/check.py --repo <path>      # 0 pass / 1 violations / 2 unreadable
python3 ~/src/utils/repo_contract/bootstrap.py --repo <path>  # print proposal
python3 ~/src/utils/repo_contract/bootstrap.py --repo <path> --write
python3 ~/src/utils/repo_contract/sweep.py                    # ~/data/claude-scratch/repo-contract/SWEEP.md
```

Bootstrap never overwrites: it appends the section (or inserts missing lines at
the end of an existing `## Commands`), creates `CLAUDE.md -> AGENTS.md` when
only AGENTS.md exists, and writes `scripts/test_changed.sh` only if absent.
Sources, in priority order: existing CLAUDE.md, `scripts/<key>.sh`, Makefile,
package.json (node only), CI workflows, stack defaults. Anything it cannot infer
is written as `<FILL IN>`, which the gate rejects until a human fills it.

## Adding the gate to a repo

Run this on every new repo right after `git init` (idempotent):

```bash
~/src/utils/scripts/install_repo_contract_gate.sh <repo>   # --check to preview
```

It writes the `scripts/check_repo_contract.sh` shim, the pre-commit hook, the
CI workflow (skipped when the repo has `.dep-freshness-no-workflow`, i.e. no
GitHub Actions), then bootstraps the `## Commands` section and
`scripts/test_changed.sh`. It exits 1 while a `<FILL IN>` remains. Never copy
`scripts/check_repo_contract.sh` from this repo (it is the real gate, not a shim).
The hook only fires on commits touching CLAUDE.md/AGENTS.md/test_changed.sh,
so a repo that never got the installer is caught only by `sweep.py`.

## Websites: the AgentReady gate

Every website kuhy owns must pass `~/src/utils/agent_ready` (decided
2026-10-22). A repo is a website when `repo-contract.toml` has an
`[agent_ready]` table, or when detection finds a node web build: a `build`
script in package.json plus a Vite or Astro config or a root `index.html`.
`check.py` fails a detected repo that has no table. Keys:
`dist = "<build dir>"` with optional `build` and `install`, or
`url = "https://..."` for server-rendered sites, or `skip = "<reason>"` for a
repo that is not a website. `act = true` turns on the act checks.

For a website, the installer also writes the proposed table (it never
overwrites one), the `scripts/check_agent_ready.sh` shim, the `agent-ready`
pre-commit hook, and `.github/workflows/agent-ready.yml`. That workflow checks
out kuhyx/utils into `.utils`, sets up Node, and runs
`check_agent_ready.sh --strict --install`. The shared gate
`scripts/check_agent_ready.sh` builds the site and runs
`agent_ready/check.sh dist|url`. The build runs in a throwaway copy of the
working tree (`isolate.py`), because a live `dist/` may be bind-mounted into
Caddy and must never be emptied by a commit. The hook only fires when a
web-relevant file is staged (`web.DEFAULT_FILES`, overridable with
`files = "<regex>"`); CI rebuilds on every push. Without `--strict`, an unreachable url
degrades to a pass, and the gate defers to that workflow when run inside
another GitHub Actions job.

## Flutter apps: the launcher rules

Decided by kuhy 2026-10-23 (`launcher.py`). They apply to every tracked
`pubspec.yaml` whose `dependencies:` pull in the Flutter SDK and that has an
`android/` dir beside it, at the root or nested (`app/`, screen-locker's
`stronglift_replacement/workout_app`). Violations are prefixed `launcher:`
(or `launcher [<app dir>]:` for a nested app).

1. **Launcher name** (`launcher_label.py`): `<application android:label>`
   of the main manifest matches `^[A-Z][A-Za-z]{0,9}$`, and so does the
   `android:label` of any activity or alias with a MAIN + LAUNCHER filter
   (it overrides the application label on the launcher). A literal,
   `@string/<name>` and `${placeholder}` are all resolved. A placeholder is
   checked at every `manifestPlaceholders` assignment in
   `android/app/build.gradle[.kts]`, except inside a variant that sets
   `applicationIdSuffix`: rule 3 hides that variant from the launcher.
   Anything unresolvable fails. The rules and messages mirror testsAndMisc
   `python_pkg/app_icons/labels.py`.
2. **Desktop name**: every tracked `*.desktop` file in the repo has a
   `[Desktop Entry] Name=` that passes rule 1.
3. **Hidden variants** (`android_manifest.py`): a buildType or flavor whose
   own gradle block sets `applicationIdSuffix` needs
   `android/app/src/<variant>/AndroidManifest.xml` removing the LAUNCHER
   category (`tools:node="remove"` on the `<category>`) from each launcher
   activity. MAIN must stay, so `am start -n` still works.
4. **Icon size** (`png_ink.py`, stdlib only): `assets/icon/icon_foreground.png`,
   when present, is 8-bit RGBA 1024x1024. Its furthest inked pixel
   (alpha > 127) sits 340px ±1% from the ink-box centre, and that centre is
   within 2px of (512, 512). This is the shared generator's `fit.py`
   measurement. An app that cannot ship the PNG declares
   `[launcher_icon] skip = "<reason>"` in a `repo-contract.toml` beside its
   pubspec, and the reason is required.

The repo-contract hook's `files:` (template `pre-commit-snippet.yaml`) also
matches every file these rules read. `install.py` never rewrites an existing
hook, so roll a widened regex out with
`python3 -m repo_contract.hook_sync [--apply] [REPO ...]` (dry run by default).

## Tests

```bash
PYTHONPATH=. python -m pytest repo_contract/tests -q --cov=repo_contract --cov-branch --cov-fail-under=100
```
