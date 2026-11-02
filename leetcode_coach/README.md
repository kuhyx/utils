# leetcode_coach

The `/leetcode` coach as a library: the Socratic method gates, the session log,
the grader and card builder, and the relay that serves them. Moved here from
`leetcode-guard` (with its git history) so the tutor server and leetcode-guard
share ONE coach. Python 3.14, `import leetcode_coach`.

Specs stay in `~/src/leetcode-guard/DOCS-coach-{spec,ui-spec,relay}.md`.

## Install

| Who | How |
|---|---|
| leetcode-guard | pinned: `leetcode-coach @ git+https://github.com/kuhyx/utils@leetcode-coach-v0.1.0#subdirectory=leetcode_coach` (its `install.sh` pip-installs it) |
| tutor server / development | `./install.sh` (editable, system python) |

Tests: `scripts/run_subproject_tests.sh leetcode_coach` (100% branch coverage).
Gate: `pre-commit run --config leetcode_coach/.pre-commit-config.yaml --all-files`.

## Layers

Stdlib only unless noted. Import only what you need.

| Layer | Modules |
|---|---|
| Gates | `phase`, `shape`, `gate_notes`, `req_check`, `leak`, `toolbox`, `stop_gate`, `gate_detector` |
| Log + progress | `session_log`, `progress`, `report` |
| Content | `fetch_problem`, `toolbox.json`, `answer_key`, `clusters.json` |
| Cards | `toolbox_cards`, `card_rules`, `make_cards` (needs genanki), `anki_connect` |
| Models | `claude_cli` (haiku/sonnet via `claude -p`), `local_backend` (Ollama) |
| Relay | `relay.*`: state machine, grading, run-code, HTTP + RTDB (needs requests, crdt-sync) |
| Clients | `leetcode_repl` (`leetcode` command), `cluster_cli`, `local_session`, `how_to` |

## Library API for the tutor server

Everything keys off the session log: a JSONL file per problem and day, state is
derived from it (never held in memory), so any caller and a restart agree.

```python
from leetcode_coach import fetch_problem, phase, session_log, toolbox, leak
```

**Statement.** `fetch_problem.fetch(slug) -> dict | None` (None / `isPaidOnly`
means paste it), `fetch_problem.render(q, lang) -> str` (markdown with
`Tags:` and `Languages available:` lines), `slug_from(url_or_slug)`.

**Phase gate (req-before-code).**
`gate = phase.PhaseGate(log, toolbox.load_safe(), source=lambda: statement, ask=None)`

- `gate.screen(block, *, is_code=None) -> (sent | None, note)`: `None` means
  refuse and show `note`; otherwise forward `sent` to the coach and show `note`
  if non-empty. Logs `req`, `req_check`, `code`, `reveal`.
- `gate.refusal_note()`, `gate.code_seen()`, `gate.events()`, `gate.sql()`,
  `gate.leaks(reply, user_texts) -> [names]` (bounce and regenerate),
  `gate.after_reply(text) -> text without the rung marker` (logs `rung`).
- `phase.req_state(events) -> ReqState(accepted, forced, tries, .open)`,
  `phase.step2_attempts(events)`, `phase.regex_verdict(block) -> bool | None`.
- 3 incomplete lists force the gate open (`req_incomplete: true` on `code`).

**Q5, SQL problems.** If the statement has the `Database` tag or offers a SQL
dialect (`shape.is_sql`), `req:` is skipped: the gate asks for an OUTPUT SHAPE,
a message starting `shape:` that says the **columns**, the **rows** (what one
row stands for) and the **grouping**. Judged mechanically
(`shape.check -> req_check.Check(verdict, missing, "shape")`, no model, never
fails open), logged as the same `req` / `req_check` events with
`via: "shape"`, forced after 3 tries like `req:`. A `req:` message on a SQL
problem counts as the shape. An unfetched statement (just a slug) is not SQL:
the stricter `req:` gate applies. Algorithm problems are unchanged.
The relay state's `session.kind` is `"sql"` or `"algorithm"`.

**Leaks and code.** `leak.leaked_names(reply, allowed, box)` (toolbox names
too early), `stop_gate.verdict(raw, reply)`, `gate_detector.offending_snippets`.

**Log.** `session_log.log_path(problem)`, `append(path, event, **fields)`,
`read(path)`, `current(events)`, `has_code(path)`. Events: `session_start`,
`req`, `req_check`, `code`, `rung`, `reveal`, `grade`, `chat`. The field set is
a FIXED contract read by `leetcode_guard._coach_log`: add a field only together
with that reader.

**Progress.** `progress.history(slug)`, `due_retests()` (cold re-tests at +3
and +10 days), `cluster_progress()`, `next_new(...)`, `cluster_of(slug)`.

**Toolbox + cards.** `toolbox.load_safe() -> Toolbox` (`.entries`,
`.properties`), `toolbox_cards.cards_for(names) -> [Card]` (property list ->
operation), `toolbox_cards.append_entry(...)` (new entry, after kuhy confirms),
`make_cards.deliver(...)` (Anki deck "LeetCode", `.apkg` fallback).

**Relay (the five-step coach).** `relay.coach.Coach(Deps(...))`:
`handle(Request) -> dict` for the seven kinds in `relay.protocol.KINDS`
(`session_start`, `session_end`, `chat`, `grade_step`, `hint`, `reveal`,
`run_code`), `state()`, `chat_after(id)`, `tick()` (Accepted probe).
`relay.app.Relay(Deps())` adds loopback HTTP (`start()`, `port`) and the RTDB
phone link (`connect_phone(make_rtdb)`). Every dependency is a `Deps` field:
`ask`, `local_chat`, `fetch`, `probe`, `run_code`, `answers`, `box`,
`state_dir`, `cards_dry_run`, `clock_ms`. The wire is `DOCS-coach-relay.md`.

## What it needs from leetcode-guard

Three read-only calls, resolved on demand in `guard_bridge` (a consumer
without leetcode-guard imports everything else; these raise
`GuardUnavailableError`, never a silent "nothing solved"):

| Call | Used by |
|---|---|
| `solved_slugs(slugs)` | `cluster_cli` (skip already-Accepted problems) |
| `recent_accepted()` | relay step 4 probe (`AcceptedProbe`, at most 1/min) |
| `phone_id_token(app, timeout_seconds=)` | `relay.__main__` RTDB sign-in |

No coach module imports `leetcode_guard` statically and no route can reach the
gate's ledger, credits or unlocks (`tests/test_guard_boundary.py` reads the
bridge's strings against an allow-list). Credit stays leetcode-guard's job.

## Environment

| Variable | Meaning |
|---|---|
| `LEETCODE_COACH_SESSIONS_DIR` | session logs (default `~/.local/share/leetcode-coach/sessions`) |
| `LEETCODE_COACH_LOG` | log the REPL exported for the Stop hook |
| `LEETCODE_COACH_CLUSTER` | cluster tag for new logs |
| `LEETCODE_CLAUDE_BIN` | the `claude` binary (tests: a fake) |
| `LEETCODE_COACH_RELAY_DIR` / `_PORT` / `_RTDB_URL` | relay state dir, port (default 8777), RTDB override |
| `LEETCODE_COACH_CARDS_DRY_RUN` | `1`: build cards, push nothing |

## Commands (the live units use these paths)

- `python3 -m leetcode_coach.relay`: the relay (leetcode-coach-relay.service)
- `python3 -P -m leetcode_coach.leetcode_repl <url>` (the `leetcode` command)
- `python3 -m leetcode_coach.stop_gate`: the Stop hook (shim in `hook_shims/`)
- `python3 -m leetcode_coach.toolbox_cards --help`, `make_cards`, `report`,
  `cluster_cli`, `fetch_problem`: the skill's scripts
- The skill body is `leetcode_coach/SKILL.md`; the skill dir
  `~/.claude/skills/leetcode` points at `leetcode_coach/leetcode_coach/`.
