# app_errors

The PC side of kuhy's app error and slow-wait reporting. Every app reports
errors, and every wait the user sees over 1 s (`perf.slow`). This ingest merges
the reports by signature and writes `~/.local/state/app-errors/<app>.json` in
the todoImplementer `contracts/app-error.schema.json` `report` shape. The board
reads that folder and turns each open error into a self-fixing ticket
(todoImplementer `DOCS-errors.md`).

Generalised from kartka's `tools/errors`. Dart signatures are byte-identical to
kartka's. See `DOCS-app-errors.md` at the repo root for the whole pipeline.

## Where reports come from

| Reporter | Runs on | Writes |
|---|---|---|
| `crdt_sync_flutter` `installErrorReporting` | phone, desktop, web | RTDB `/<app>/errors/<device>/<id>` |
| `gatelock.error_report.install` | PC (Tk) | spool `~/.local/state/app-errors-spool/<app>.jsonl` |
| Godot `addons/app_errors` (`godot_dev_tools/`) | PC | the same spool |

The ingest skips `kartka` in RTDB, because kartka still runs its own ingest.

## Entry (one report, every language)

`at` (ISO UTC), `kind` (`uncaught.flutter`, `uncaught.python`, `uncaught.gdscript`,
`ui.snackbar`, `perf.slow`, ...), `error`, `stack` (list of frames), plus these
optional fields:

- `repo` (`owner/name`, default `kuhyx/<app>`)
- `mark` (the substring that marks the app's own frames: `package:todo/`,
  `leetcode_guard/`, `res://`)
- `route`
- `operation`, `durationMs`, `waitId` and `still` (slow waits)
- `build` (versionCode, 0 when unknown) and `version`

## Commands

```bash
app-errors ingest              # what the timer runs every 5 min
app-errors ingest --keep       # leave RTDB entries in place
app-errors ingest --no-rtdb    # local spool only
app-errors resolve <app> <signature>   # mark it fixed; a newer build reopens it
```

`app_errors/install.sh` installs the venv
(`~/.local/share/app-errors/venv`), the `app-errors` link and
`app-errors-ingest.timer`. `scripts/deploy.sh` runs it.

RTDB access reuses an already seeded crdt-sync session (`--session`, default
`firebase_backup`), so the ingest needs no sign-in of its own.

Tests: `cd app_errors && python -m pytest` (100 % branch coverage).
