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

## Tests

```bash
PYTHONPATH=. python -m pytest repo_contract/tests -q --cov=repo_contract --cov-branch --cov-fail-under=100
```
