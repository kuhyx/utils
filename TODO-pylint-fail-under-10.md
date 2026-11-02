# TODO — pylint `--fail-under=10` everywhere, and clear what that surfaces

REMOVE ME AFTER FINISH

## what

Two pylint hooks (`leetcode-guard`, `steam-backlog-enforcer`) still pass at
`--fail-under=8.0`, which permanently tolerates two points of lint debt and
lets a score *regress* from 9.9 to 8.1 without failing anything. Move both to
`10`, and fix what that surfaces. Every other site already runs at `10`, so
this is adopting an existing standard, not inventing one.

## what is left (updated 2026-11-02)

Done and verified (`pre-commit run pylint --all-files`, exit 0, each at
`--fail-under=10`): `control-panel`, `screen-locker` (both hooks),
`testsAndMisc/meta`, `utils/crdt-sync`, `utils/freedays`, `utils/gatelock`,
`utils/music_theory`.

Still at `--fail-under=8.0`:

| Repo | Site |
|---|---|
| `leetcode-guard` | `.pre-commit-config.yaml:126` |
| `steam-backlog-enforcer` | `.pre-commit-config.yaml:126` (ignore its `.claude/worktrees/` copies) |

Both live outside `utils`, so this file belongs to whichever session works
those repos. The method is the fleet standard: pylint grades source, ruff
grades tests. Copy the `[tool.pylint]` block (tests basename ignore,
`init-hook = "import sys; sys.path.insert(0, '.')"`) from `wake-alarm` /
`diet-guard`, bump to `10`, fix the residue in source. Read the `must`
rules below first.

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
! grep -rn --exclude-dir=worktrees --include=.pre-commit-config.yaml --include=.pylintrc \
    -E 'fail-under=(8|9)' ~/src ~/praca_magisterska 2>/dev/null \
  | grep -v cov-fail-under

# 2. both remaining packages pass its own pylint hook
for d in ~/src/leetcode-guard ~/src/steam-backlog-enforcer; do
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
