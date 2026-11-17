# App errors and slow waits become board tickets

kuhy's rule (2026-11-17): every error, and every wait the user sees over 1 s, in
any of his apps is reported automatically. The board then turns each one into a
ticket that fixes itself. This doc covers the apps' half and the PC ingest. The
board's half is todoImplementer `DOCS-errors.md`, with the contract in
`contracts/app-error.schema.json`. The design is kartka's pipeline
(`~/src/kartka`, `docs/DOCS-error-reports.md`), made shared.

## Pipeline

1. **Apps report.** Each report is one *entry* (see `app_errors/README.md`):
   - Flutter, `crdt_sync_flutter` 0.9.0: `installAppErrors` hooks
     `FlutterError.onError` and `PlatformDispatcher.onError`. `WaitWatch` turns
     a spinner shown over 1 s into `perf.slow`. The device deduplicates (30 s,
     20 a minute) and redacts each report, and queues it in
     `SharedPreferences`. It uploads to RTDB `/<app>/errors/<device>/<id>` with
     the build (versionCode).
   - Python/Tk, `gatelock` 0.15.0: `gatelock.error_report.install` hooks
     `sys.excepthook`, `threading.excepthook` and Tk callback errors.
     `watch_stalls(root, rep)` reports a frozen Tk loop over 1 s.
     `rep.wait(...)` and `rep.begin(...)` time a wait.
   - Godot, `godot_dev_tools` 0.2.0, `addons/app_errors`: an `OS.add_logger`
     logger catches script errors and `push_error`. A frame over 1 s, or
     `report_wait` over 1 s, becomes `perf.slow`.
   - PC apps (Tk and Godot) append to the local spool
     `~/.local/state/app-errors-spool/<app>.jsonl`. They need no RTDB, because
     the ingest runs on the same PC.
2. **The PC ingests.** `app-errors-ingest.timer` runs `app-errors ingest` every
   5 min. It reads RTDB through an already seeded crdt-sync session
   (`firebase_backup`) and reads the spool. It merges reports by signature
   (Dart signatures are kartka-identical), deletes what it read, and writes
   `~/.local/state/app-errors/<app>.json` as a contract `report`.
3. **The board files tickets.** It scans that folder every 60 s and makes one
   ticket per `app:signature` (todoImplementer `DOCS-errors.md`).

`app-errors resolve <app> <signature>` sets `open: false`. A later report opens
the error again only when it is a regression: a newer build when both sides
know the build, else a report made after the resolve. The board never calls
`resolve` on its own, because folder sources have no resolve hook. It tracks
shipped fixes by `fixed_build`.

## Choices made (no questions asked, per the brief)

- kartka keeps its own ingest for now. The shared ingest skips `/kartka`, and
  the board's `kartka` adapter still reads kartka's `state.json`. Two readers
  would race on deletes. To move kartka over, switch the board's default
  source off (`error_sources`) and retire `kartka-errors.timer`. Its ticket
  ids stay the same, because the signatures match.
- Tk and Godot use the local spool instead of RTDB: they only run on the PC.
- The Godot reporter is its own addon folder, mounted in every build. It is
  not part of `dev_tools`, which only loads for `--dev` runs.
- Reporting is silent: no text, dialog or notification in any app.

## Install and check

`scripts/deploy.sh` runs `app_errors/install.sh`. That installs the venv and
`~/.local/bin/app-errors`, enables the timer, and checks that the timer is
active and the venv imports the live checkout.
