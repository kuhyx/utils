# feedback_inbox

Turns every game's dev-feedback bundle into one todo-app task, so feedback
kuhy saves with F12 is never forgotten.

A game saves `~/data/<repo>_binaries/feedback/<stamp>/` (`report.json`,
screenshots, logs) and appends a ready-to-run Claude prompt to
`feedback-<date>.md` beside it. This package imports each complete bundle once
as a task in the todo app for `kuhyx/<repo>`.

## Task shape

- Title: `MANUAL WORK REQUIRED: <repo> feedback: <first line of his note>` (note capped
  at 120 characters). The prefix makes todoImplementer list it as a human part and never
  run it. No note: `... feedback: <game> <combo> <HH:MM>`. A `report.json` that does
  not parse still gets a task, tagged `[corrupt report.json]`; the note then
  comes from the markdown entry.
- Body: a `Due: <next day 10:00>` line, then the bundle's markdown entry (the
  prompt with absolute paths).
- The task is its own note (`add_task` with `new_note`). The server stores that as
  `<repo> todos: <title>` plus a `## <title>` section, so right after adding, the inbox
  rewrites it with `update_task` to the exact title and a section-free body (the entry's
  own `##` headings become `###`). todoImplementer splits notes at `## ` headings, and a
  title that does not start with `MANUAL WORK REQUIRED: ` would make a runnable part.
  The marker records `format: 2` once the rewrite worked; a failed rewrite is retried on
  the next sweep (never a second task), and markers without it are repaired the same way.
- Closing the task cancels the feedback. "Act on feedback" in a Claude session
  means working every open `<repo> feedback:` task.

The todo app has no due-date or reminder field yet, so the due time is only
text in the body.

## How it runs

| Unit | Does |
|---|---|
| `feedback-inbox.path` | `PathChanged` on every existing `*_binaries/feedback` folder; runs `feedback-inbox run` |
| `feedback-inbox-sync.path` | `PathChanged` on `~/data` and every `*_binaries` folder; runs `sync` then `run` |
| `feedback-inbox-sync.timer` | every 5 min, the same sweep (events during a run are lost by `.path` units) |

`.path` units take no globs: `feedback-inbox sync` writes the folder list into
the drop-ins `feedback-inbox{,-sync}.path.d/dirs.conf` and reloads systemd only
when the set of games changed.

A bundle is complete when `report.json` is at least 2 s old and its markdown
entry exists (matched by the stamp folder in the entry's paths). Incomplete
bundles are retried; `run` waits up to 15 s for them.

The import marker is `.inbox-imported.json` inside the bundle (task id, title,
due). It is written only after the todo server accepted the task, so a server
outage leaves no marker, exits non-zero, and the next sweep retries.

## Install

```bash
scripts/run_subproject_tests.sh feedback_inbox   # from the monorepo root
feedback_inbox/install.sh
```

`install.sh` builds a stdlib-only venv, links `feedback-inbox` into
`~/.local/bin`, mints a todo-server token into `~/.config/feedback-inbox/token`
(0600; revoke by deleting its line in `~/.config/todo-mcp/tokens`) and enables
the units. Enabling sweeps once, so existing bundles are imported then.

## Tests

`pytest` from this directory (100 % branch coverage enforced). Tests use a temp
`HOME`, a fake todo client, and a local HTTP server for the MCP client; the
autouse `conftest.py` redirects the one path resolver and points the todo URL
at a dead port.
