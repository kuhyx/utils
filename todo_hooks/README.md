# todo_hooks

Wires git to the todo app's MCP server (stdlib only, Python 3.14).

| Command | What it does |
|---|---|
| `closer` | post-commit: for each `Todo: <id>` trailer of HEAD, run the note's `done_check` and `close_task` on exit 0 |
| `sweep [--dry-run] [--report P] [--trust-file P]` | nightly: list open notes whose trusted `done_check` already passes, write `~/.local/state/todo-drift/report.txt` |
| `trust <id8>` / `trust --seed-open` | approve a note's `done_check` (or all currently open ones) |
| `import-pr post-merge \| post-rewrite [rebase] \| --range A..B` | add a task per `- title \| done_check: cmd` item under a merged PR's `## Todo:` heading |

Run as `scripts/todo_hooks.sh <command>` or `PYTHONPATH=<utils> python3 -m todo_hooks <command>`.

## Safety

- A `done_check` runs only if `sha256(done_check.strip())` is in `~/.config/todo-hooks/trusted-checks`. Cloud sessions can add notes, so an untrusted check is never executed.
- The note's `repo` must equal `kuhyx/<origin repo name>`.
- A note with a `Check: manual` line is never auto-closed; it is listed as "close by hand".
- Hooks fail open: server down, bad token or no `gh` prints one warning and exits 0.

## Server

`TODO_MCP_URL` (default `http://127.0.0.1:8735/mcp`), token from `TODO_MCP_TOKEN` else `~/.config/todo-mcp-client/token` (0600). Handshake: `initialize`, `notifications/initialized`, then `tools/call`, all with the `Mcp-Session-Id` the first reply returns.

## Wiring a repo

```yaml
repos:
  - repo: https://github.com/kuhyx/utils
    rev: main
    hooks: [{id: todo-closer}, {id: todo-import-pr-merge}, {id: todo-import-pr-rewrite}]
default_install_hook_types: [pre-commit, pre-push, post-commit, post-merge, post-rewrite]
```

Each clone needs the post-* hook types installed: the `default_install_hook_types` line above, or `pre-commit install -t post-commit -t post-merge -t post-rewrite`.

## Nightly sweep

`systemd/todo-drift.service` and `.timer` (03:00) are files only; install with `systemctl --user link` plus `enable --now todo-drift.timer`.

## Tests

`python3 -m pytest todo_hooks -q --cov=todo_hooks --cov-config=todo_hooks/.coveragerc`
