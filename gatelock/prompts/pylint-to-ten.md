# Session prompt: take gatelock's pylint from 9.06 to 10.00

Paste everything below the line into a fresh Claude Code session started in
`~/utils` (the monorepo root — **not** `~/utils/gatelock`; pre-commit runs
hooks from the git root and every path in the hook config is relative to it).

---

Take `gatelock`'s pylint score from **9.06/10 to a clean 10.00/10**, without
weakening the linter.

## Why

The pylint hook runs with `--fail-under=8.0`, so 9.06 passes while carrying
~394 findings. The same job was done in the sibling package
`~/utils/crdt-sync` on 2026-08-21 (8.58 -> 10.00), so the conventions and the
gate are already proven one directory over — read that package's
`crdt_sync/tests/conftest.py` and the commits `1b8c99d` / `2005c40` in
`~/utils` for the worked example.

Measured on this machine, 2026-08-21, with
`~/.cache/pre-commit/repo01lfw04p/py_env-python3/bin/pylint --rcfile=pyproject.toml gatelock`
run from `~/utils/gatelock`:

| category | count |
|---|---|
| redefined-outer-name | 171 |
| protected-access | 141 |
| missing-function-docstring | 19 |
| use-implicit-booleaness-not-comparison-to-zero | 14 |
| use-implicit-booleaness-not-comparison | 12 |
| unbalanced-tuple-unpacking | 9 |

**312 of the top two categories are in `gatelock/tests/`.** This repo is NOT
the docstring problem the other two are — only 19 docstrings are missing.
It is dominated by **pytest fixture idiom**, which makes it a different job:

- `redefined-outer-name` (171) is the classic fixture-shadowing pattern — a
  test parameter named the same as the module-level fixture function.
- `protected-access` (141) is tests reaching into the private members that
  are the unit under test.

Note for context: `~/screen-locker`'s tests hook already disables
`protected-access` / `unused-argument` / `duplicate-code` for exactly this
reason. gatelock does not, and that gap is most of the 0.94.

Re-measure before you start and again at the end.

## Scope

**In scope**
1. Every pylint finding under `gatelock/`.

**Out of scope — do not touch**
- `--fail-under` in `gatelock/.pre-commit-config.yaml`. Do NOT raise it to
  hide a shortfall, and do NOT lower it. Leave it at 8.0.
- Any sibling package in the monorepo — `crdt-sync/`, `web_ui/`,
  `design_system/`, `sync_settings_ui/`. Stage narrowly: `gatelock/` only.
- Note `crdt-sync/tool/seed_session.py` is modified and
  `crdt-sync/firebase-debug.log` is untracked; both predate this task. Keep
  them out of your commit.

## The decision this task actually turns on

The 312 fixture-idiom findings are not individually fixable in any
satisfying way, and this is the fork to bring to the user **before** doing
the work, not after:

- **Option A — configure the checks off for tests only.** Add a
  `[tool.pylint...]` per-path setting or a tests-scoped disable for
  `redefined-outer-name` + `protected-access`. This is what screen-locker
  already does, it is honest (the checks are wrong for pytest, not the code),
  and it is one reviewable decision instead of 312 edits. It IS a config
  change, which the user has previously refused when the alternative was
  real work — so it must be asked, with the screen-locker precedent cited.
- **Option B — rename every shadowing parameter** and re-examine all 141
  protected accesses individually. No config change; a very large diff
  touching most of the test suite.

Ask which, in one question, with A recommended and the precedent named. Do
not start either until answered.

## The rule for everything else

**Fix the underlying issue; do not suppress it.** The repo blocks `noqa` and
`type: ignore` outright. Inline `# pylint: disable=` is permitted only for a
genuine false positive, scoped to the narrowest unit, placed on the line
that actually triggers it (verify — a `disable-next` one line off silently
does nothing and pylint reports `useless-suppression`), with a comment
saying why.

`unbalanced-tuple-unpacking` (9) is worth reading carefully rather than
suppressing: it sometimes flags a real latent IndexError.

## Gates

- `python -m pytest -q` from `~/utils/gatelock` — **389 passing at 100%
  branch coverage** (measured 2026-08-21). Both numbers must hold.
- `pre-commit run --config gatelock/.pre-commit-config.yaml --files <changed>`
  — run it from `~/utils`, and note the config's `files:` filter means paths
  must be repo-root-relative (`gatelock/...`) or the hooks silently skip.
- `ruff format` will reformat what you touch; re-run the suite afterwards.

## Done means

1. pylint reports **10.00/10** for `gatelock`.
2. `--fail-under` still 8.0.
3. 389 tests still passing at 100% branch coverage.
4. No sibling package appears in your diff.
5. The final report states which option the user chose for the fixture-idiom
   findings, and lists every suppression with its justification.
