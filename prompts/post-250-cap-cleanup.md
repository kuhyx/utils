> **This file is a ready-to-use prompt.** Open this repo (`~/utils`) and say
> "do post-250-cap-cleanup". It is self-contained -- it needs no context from
> any other session.
>
> Generated 2026-08-22 at the end of the session that finished
> `refactor_claude_todo.md` (the 250-line cap). Everything below was measured
> in that session; **re-verify each figure before trusting it**, since the
> numbers are a snapshot.

## ⛔ WHEN YOU FINISH THIS PROMPT

Delete this file and commit that deletion together with the work:

```bash
git rm prompts/post-250-cap-cleanup.md
```

A finished prompt left in the repo is indistinguishable from a pending one,
and the next session will re-run it. If you complete only some of the four
tasks, do **not** delete it -- strike through the finished ones instead and
leave the rest.

## Context

The 250-line file cap is done and enforced: `bash
scripts/check_file_length.sh --all` exits 0, a pre-commit hook blocks an
over-cap commit, and `.github/workflows/file-length.yml` runs the same check
on push. **Do not undo any of that.** Every new file this prompt creates must
also stay at or under 250 lines -- the hook will block your commit otherwise,
which is the point.

Four loose ends were deliberately left. They are independent; do them in any
order, and commit each separately.

---

## Task 1 -- make `web-ui-tests` green (`pnpm build`)

**Status:** red since commit `6714d13`, which pre-dates the cap work.

The job's failing step:

```yaml
- name: dist/ is in sync with src/
  run: |
    pnpm build
    if ! git diff --exit-code -- dist; then
      echo "::error::dist/ is stale — run 'pnpm build' in web_ui and commit the result."
      exit 1
```

So `web_ui/dist/` is a committed build artifact that has drifted from `src/`.

```bash
cd ~/utils/web_ui
pnpm install    # only if node_modules is missing
pnpm build
git diff --stat -- dist
```

Then run the repo's own suite before committing (`pnpm test`, or whatever
`web_ui/package.json` defines -- read it, don't guess), and check the built
output is not itself over the cap: `bash ../scripts/check_file_length.sh --all`.
If a generated file in `dist/` trips the cap, **do not split it** -- generated
files are exempt by design; add the exemption in `file_length/_tables.py`
(`is_generated` / the `GENERATED` header rule) rather than hand-editing build
output.

`pnpm` is at `~/.local/share/pnpm/pnpm` and node is `v24.18.0` via nvm; both
were on PATH as of 2026-08-22.

**Done when:** `pnpm build` produces no `git diff` in `dist/`, the web_ui
suite passes locally, and the `web_ui tests` workflow goes green on push.

---

## Task 2 -- put `crdt-sync/tool/` under test at 100% coverage

**Read this scope note before starting; it is bigger than it first looks.**

`crdt-sync/pyproject.toml` measures `--cov=crdt_sync` with
`source = ["crdt_sync"]`, so the whole `tool/` package is currently
unmeasured. The trigger for this task was `tool/_oauth_callback.py` (105
lines, extracted during the cap work, whose `_start_callback_server` runtime
path is unexercised) -- but adding `tool` to the coverage source pulls in
**seven modules, ~1350 lines**, none of which have tests today:

| lines | file |
| ----: | :--- |
|   250 | `tool/seed_session.py` |
|   243 | `tool/link_google.py` |
|   233 | `tool/google_id_token.py` |
|   216 | `tool/migrate_github_to_firebase.py` |
|   212 | `tool/preflight_firebase.py` |
|   105 | `tool/_oauth_callback.py` |
|    89 | `tool/interop_seed.py` |
|     6 | `tool/__init__.py` |

The bar in this repo is **100% branch coverage, and omitting packages from
coverage is forbidden** (`~/.claude/memories/code-quality.md`: "NEVER omit
packages from coverage. Write tests for everything." and "even if it takes
hours"). So the honest shape of this task is: test all of `tool/`, not just
the one file.

**Suggested order** -- land each as its own commit so partial progress is
useful:

1. `_oauth_callback.py` first. It is the reason this task exists and the only
   one with no network dependency: `_free_port` binds a real socket,
   `_CallbackHandler` can be driven with a fake request, and
   `_start_callback_server` can be exercised against `http.client` on the port
   it picks. Do this one even if you do nothing else.
2. `google_id_token.py` -- `fetch_id_token` is a `requests` call; mock at the
   session boundary the way `crdt_sync/tests/test_firebase_auth.py` already
   does. `main()` is argparse; test it via `main(["--client-id", ...])`.
3. The rest, largest-payoff first.

Only after every module is covered, flip the config:

```toml
addopts = [..., "--cov=crdt_sync", "--cov=tool", ...]
[tool.coverage.run]
source = ["crdt_sync", "tool"]
```

Flipping it earlier makes the suite fail on the 100% gate for every module you
have not reached yet, which blocks unrelated commits -- so it is the **last**
step, not the first.

**Traps, all hit during the cap work:**

- Tests live in `crdt-sync/crdt_sync/tests/`, and `testpaths` points there. A
  `tool/` test still belongs under that directory (e.g.
  `crdt_sync/tests/test_tool_oauth_callback.py`) unless you also extend
  `testpaths` -- decide once and be consistent.
- `tool` is imported as a package from the `crdt-sync` root
  (`python3 -m tool.google_id_token`, and `seed_session.py` does
  `from tool.google_id_token import ...`). Do not "fix" those to relative
  imports.
- Do **not** add `# noqa` or `# type: ignore` anywhere; the repo bans them and
  a pre-commit hook blocks them. If lint fights you, fix the code.
- Run the CI-pinned ruff, not whatever `ls | head -1` finds. The cache holds
  three versions and CI pins **0.15.2**:
  `/home/kuhy/.cache/pre-commit/repodhz30fnk/py_env-python3/bin/ruff`.
  Confirm with `--version`; 0.14.5 misses findings that fail CI.
- Verify with `bash scripts/check_file_length.sh --all` and
  `pre-commit run --config crdt-sync/.pre-commit-config.yaml --all-files`
  (the `--all-files` run catches ruff pruning re-export imports, which broke
  `import crdt_sync` three times during the cap work).

**Done when:** `source = ["crdt_sync", "tool"]` is in effect and
`bash scripts/run_subproject_tests.sh crdt-sync` still reports 100% with the
suite green. Baseline before you start: **259 passed, 100%**.

---

## Task 3 -- resolve the three dirty working-tree items

All three predate the cap work and were deliberately left untouched. **Look at
each before acting -- one of them is real work, not junk.**

### `crdt-sync/tool/seed_session.py` (modified, +10/-1)

This is a **real, intentional change**: it adds `todo` to `DEFAULT_APPS` and
documents why (todo grew a desktop wrapper with its own Firebase REST client
that needs a session like the Python daemons do). Someone wrote this on
purpose and did not commit it.

The comment asserts specific files exist, and **both were confirmed present on
2026-08-22**:

```bash
ls ~/todo/lib/desktop/wrapper_server.dart ~/todo/lib/sync/firebase_backend.dart
```

Re-run that (cheap), and if it still holds, commit the change as its own
commit with a message explaining the `todo` addition. If the files have since
moved, the comment is stale -- ask rather than guessing.

### `crdt-sync/firebase-debug.log` (untracked, 1931 lines)

Firebase CLI debug output from 2026-08-11. Pure tool exhaust, and **not
gitignored** -- which is the actual bug, since it will keep reappearing. Add
`firebase-debug.log` to the appropriate `.gitignore` and delete the file. Do
not commit its contents.

### `staged/` (untracked directory)

`staged/phone_deploy_split/` holds a prepared-but-unapplied split of
`~/.claude/scripts/phone_deploy.sh` plus an `APPLY.sh`. Read
`staged/phone_deploy_split/README.md` first: it was staged because that
session could not write to `~/.claude` non-interactively.

Two of its notes are now **out of date** and should be corrected or dropped:
its `.pre-commit-config.yaml` snippet uses an absolute
`/home/kuhy/utils/scripts/check_file_length.sh` path (that form exits 127 on a
CI runner -- `~/utils` now uses a repo-relative `entry:`), and it claims
`refactor_claude_todo.md`'s violations table is stale, which is true but moot
now that the task is done.

Decide with the user: apply it (`bash staged/phone_deploy_split/APPLY.sh`,
which needs interactive approval for `~/.claude` writes), commit it into
`~/utils` as a tracked staging area, or delete it. **Do not silently delete
it** -- it represents real verified work (shellcheck clean, 12/12 function
parity, exit codes checked).

---

## Task 4 -- fix the stale skill pointer (outside this repo)

`~/.claude/skills/unified-design-system/SKILL.md` describes
`unified-design-system/README.md` as holding "rules, per-stack patterns,
'Do NOT' list". The per-stack patterns moved to
`unified-design-system/operability-patterns.md` during the cap work, and the
operability rules to `operability.md`.

Nothing is broken -- every filename the skill links still exists -- but a
future session following that description lands in the wrong file. Update the
file list to include `operability.md` and `operability-patterns.md`.

This edits `~/.claude`, which the harness guards as sensitive config, so it
may need interactive approval. If it does, tell the user the exact edit rather
than working around it.

---

## Verify (all four)

```bash
cd ~/utils
bash scripts/check_file_length.sh --all                  # must exit 0
bash scripts/run_subproject_tests.sh crdt-sync           # 100% coverage
pre-commit run --config crdt-sync/.pre-commit-config.yaml --all-files
git status --short                                       # should be empty
gh run list --limit 10                                   # web_ui tests green
```

`web-ui-tests` is the one workflow that was red before this prompt; the other
nine were green as of 2026-08-22.
