# TODO — pylint `--fail-under=10` everywhere, and clear what that surfaces

REMOVE ME AFTER FINISH

## what

Ten pylint hooks across six repos still pass at `--fail-under=8.0`, which
permanently tolerates two points of lint debt and lets a score *regress* from
9.9 to 8.1 without failing anything. Move every one to `10`, and fix what
that surfaces. Five other sites already run at `10`, so this is adopting an
existing standard, not inventing one.

## the ten sites, exact

Measured 2026-09-12. "Score now" is that package's current rating under its
own config, tests included.

| Repo / package | Site | Score now |
|---|---|---|
| `control-panel` | `.pre-commit-config.yaml:159` | 8.53 |
| `leetcode-guard` | `.pre-commit-config.yaml:112` | 8.71 |
| `screen-locker` | `.pre-commit-config.yaml:121` | 9.85 |
| `screen-locker` | `.pre-commit-config.yaml:140` | (2nd pylint hook) |
| `steam-backlog-enforcer` | `.pre-commit-config.yaml:124` | 8.76 |
| `testsAndMisc/meta` | `.pre-commit-config.yaml:194` | 8.77 |
| `utils/crdt-sync` | `.pre-commit-config.yaml:111` | 9.59 |
| `utils/freedays` | `.pre-commit-config.yaml:109` | 8.55 |
| `utils/gatelock` | `.pre-commit-config.yaml:109` | 9.18 |
| `utils/music_theory` | `.pre-commit-config.yaml:113` | 8.54 |

`screen-locker` has **two** pylint hooks; both need the bump or the second one
silently keeps the old bar.

Already at `10` — do not touch, these are the reference:
`build-your-x`, `diet-guard`, `testsAndMisc` (root config),
`wake-alarm`, `WUT_Computer_Science/.../translator/.pylintrc`.

## why the scores look bad, and why that is misleading

Every one of these configs runs `enable = "all"` with `disable = []` — the
strictest pylint setting there is, including checks that are off by default.
The raw findings are dominated by **test-file idioms**, not source defects.
Measured on the four `utils` packages:

```
crdt-sync     54 protected-access, 50 redefined-outer-name, 18 duplicate-code
freedays     100 missing-function-docstring, 14 implicit-booleaness
gatelock     147 redefined-outer-name, 142 protected-access
music_theory 112 missing-function-docstring, 14 missing-module-docstring
```

`redefined-outer-name` at that volume is pytest fixtures. `protected-access`
is tests reaching into internals on purpose. Neither is a defect.

**The repos already at 10 solved this and wrote down why.** From
`wake-alarm/pyproject.toml`, verbatim:

> `ignore = [".venv", "__pycache__", "tests"]` — "tests" is a basename match:
> test suites intentionally use patterns (protected-access, magic-value
> comparisons) that don't apply to source code, matching testsAndMisc's
> pylint scope (tests are linted by ruff, not pylint there either).

So the fleet standard is: **pylint grades source, ruff grades tests.** The ten
sites above are the outliers that never adopted it. Their `ruff` config
already carries the equivalent test exemptions
(`"**/tests/**/*.py" = ["ARG", "D", "PLC0415", "PLR2004", "S101", "SLF001"]`),
so tests stay linted — by the tool that has the right rules for them.

## what is actually left after adopting the fleet config

Measured: `pylint --ignore=.venv,__pycache__,tests` plus wake-alarm's
three-item `disable` list, run over source files only.

| Package | Score | Remaining findings |
|---|---|---|
| `crdt-sync` | 9.93 | 5 wrong-import-position, 3 duplicate-code, 1 too-many-locals, 1 invalid-name |
| `freedays` | 9.63 | 3 import-error, 1 broad-exception-caught |
| `gatelock` | 9.88 | 6 missing-function-docstring, 4 wrong-import-position, 3 too-many-instance-attributes, 3 import-outside-toplevel, 2 broad-exception-caught, 1 each too-many-arguments / invalid-name / duplicate-code / disallowed-name / chained-comparison |
| `music_theory` | 9.42 | 10 import-error |

That is ~47 real findings across four packages, not the ~600 the raw run
suggests. **`import-error` is almost certainly config, not code**: every repo
already at 10 carries an `init-hook` the 8.0 repos lack —

```toml
init-hook = "import sys; sys.path.insert(0, '.')"
```

Try that first on `music_theory` and `freedays` before editing any import.

## must

- Every site at `--fail-under=10`. No `9.5`, no per-repo exception.
- Adopt the reference config from `wake-alarm` / `diet-guard`: the `tests`
  basename ignore, the `init-hook`, and only then the residue fixes.
- Fix findings in source. Prefer the fix to the disable, every time.
- must not: add a `# pylint: disable=` comment, or extend `disable = [...]`
  beyond wake-alarm's three implicit-booleaness entries, **without asking
  kuhy first — every time, per `memories/code-quality.md`.** All seven
  "unavoidable" disables in a past konbini-67 session were reverted.
- must not: exclude a source file from pylint to raise the score, or drop
  `enable = "all"`.
- must not: touch the five sites already at `10`.
- optional: `duplicate-code` findings may be genuine shared-code candidates
  for `utils`. Note them, do not force a refactor to hit the number.

## done

Both commands, from `~`:

```bash
# 1. no site left below 10 (cov-fail-under is coverage, not pylint)
! grep -rn --include=.pre-commit-config.yaml --include=.pylintrc \
    -E 'fail-under=(8|9)' ~/src ~/praca_magisterska 2>/dev/null \
  | grep -v cov-fail-under

# 2. every one of the nine packages passes its own pylint hook
for d in ~/src/control-panel ~/src/leetcode-guard ~/src/screen-locker \
         ~/src/steam-backlog-enforcer ~/src/testsAndMisc/meta \
         ~/src/utils/crdt-sync ~/src/utils/freedays \
         ~/src/utils/gatelock ~/src/utils/music_theory; do
  (cd "$d" && pre-commit run pylint --all-files) || echo "FAIL $d"
done
```

Command 1 prints nothing and exits 0; command 2 prints no `FAIL` line.

## verify

Desktop. Per repo, `pre-commit run --all-files` must be green — not just the
pylint hook, since a fix that satisfies pylint can break `ruff`, `mypy` or the
250-line cap. Then the test suite: these are behaviour-affecting edits
(`broad-exception-caught` and `import-outside-toplevel` fixes especially), and
every one of these packages holds a 100% coverage bar.

`utils` and `testsAndMisc` each have CI; push and confirm green rather than
trusting the local run. `gatelock`'s Tk suite is flaky on a live X session —
run it under `xvfb-run -a` and compare against a baseline worktree before
blaming a change for a failure.

## read first

- `~/src/wake-alarm/pyproject.toml` — `[tool.pylint]`, the reference config.
  `diet-guard` is byte-similar; `build-your-x` also ignores `conftest.py`.
- `~/.claude/memories/code-quality.md` — the suppression rule that governs
  every `disable` decision in this task.
- `~/src/utils/rules/` is not involved; this is not a dependency change.

Each repo is its own git repo: commit per repo, work on `main`, stage
narrowly. `utils` additionally runs the shared `md-naming` and file-length
gates, so delete this file in that repo's final commit.

REMOVE ME AFTER FINISH
