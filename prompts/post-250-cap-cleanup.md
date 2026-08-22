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

**Current state: only Task 2 is left.** Delete this file once `tool/` is
covered and the config flip has landed -- not before.

## Context

The 250-line file cap is done and enforced: `bash
scripts/check_file_length.sh --all` exits 0, a pre-commit hook blocks an
over-cap commit, and `.github/workflows/file-length.yml` runs the same check
on push. **Do not undo any of that.** Every new file this prompt creates must
also stay at or under 250 lines -- the hook will block your commit otherwise,
which is the point.

Four loose ends were deliberately left. **Three are now done** (1, 3 and 4 --
see the struck-through sections, which record what was actually found; the
prompt's original diagnosis was wrong for both 1 and 4). **Only Task 2
remains.**

---

## ~~Task 1 -- make `web-ui-tests` green~~ -- DONE (53f2816)

The diagnosis above was wrong, so it is replaced rather than struck through.
`dist/` had not drifted: all 16 files were byte-identical to a fresh build
except for a **trailing newline** that `tsc` does not emit.

At `03bf1ed` the subproject config had no `exclude`, so pre-commit's
`end-of-file-fixer` appended a newline to each generated file. `eaa5683` added
`exclude: ^web_ui/dist/` so it would not recur, but never reverted the
newlines already committed -- leaving a `dist/` that no `pnpm build` could
reproduce, and a job that could never pass.

It looked fine locally because `tsc -b` is incremental: with a warm
`tsconfig.tsbuildinfo` it skips emit entirely, so `pnpm build` was a no-op and
showed no diff. CI has no cache, always emits, always failed. To reproduce
locally, delete `web_ui/tsconfig.tsbuildinfo` first -- otherwise you are
testing nothing.

Fixed by committing the real `tsc` output. Verified green on CI (run
32578353684), `pnpm lint` clean, `pnpm coverage` 84 tests / 100%.

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

## ~~Task 3 -- resolve the three dirty working-tree items~~ -- DONE

- **`seed_session.py`** -- both files its comment cites were re-confirmed
  present, so the change was committed as-is (9d638fb).
- **`firebase-debug.log`** -- deleted, and the root `.gitignore` now covers it
  plus the sibling logs the Firebase CLI writes (e0eef3d).
- **`staged/`** -- the user chose *apply*. `APPLY.sh` installed the split into
  `~/.claude` (committed there as e0cf24a): `phone_deploy.sh` 311 -> 140 lines
  with three sourced libs, 12/12 function parity, and the unreachable-device
  path still exiting 30. `staged/` was then removed; the pre-split original
  remains recoverable from `~/.claude` at `80cd45e`.
  **Still unverified:** the build/install/launch tail, which needs a real APK
  install on the phone (`bash ~/.claude/scripts/phone_deploy.sh ~/todo
  --release`).

---

## ~~Task 4 -- fix the stale skill pointer~~ -- DONE (~/.claude e0cf24a)

The description above was partly wrong: `README.md` **does** still hold the
per-stack patterns and the "Do NOT" list. What actually split out during the
cap work was the pointer-free-operability and screen-size material, into
`operability.md` (rules) and `operability-patterns.md` (per-stack code);
README's "Pointer-free + small-screen" section is now a stub pointing at them.

`~/.claude/skills/unified-design-system/SKILL.md` now lists both new files and
tells the reader to read `operability.md` before building any interactive
widget, since its rules are marked required. All six relative links were
checked to resolve. This edit lives outside `~/utils`, so `git status` here
will never show it.

---

## Verify (all four)

```bash
cd ~/utils
bash scripts/check_file_length.sh --all                  # must exit 0
bash scripts/run_subproject_tests.sh crdt-sync           # 100% coverage
pre-commit run --config crdt-sync/.pre-commit-config.yaml --all-files
git status --short                                       # should be empty
gh run list --limit 10                                   # all workflows green
```

`web-ui-tests` was the one red workflow; it went green at 53f2816. Note that
`git status` here cannot see the Task 3/4 edits under `~/.claude` -- those are
committed in that repo (e0cf24a), not this one.

One finding outside the four tasks, left for the user to decide:
`~/.claude/scripts/finish.sh` is **309 lines**, over the cap. It does not
block anything today -- the hook checks staged files only, so it fires only if
a commit stages that file -- but it is the last known over-cap file in that
repo.
