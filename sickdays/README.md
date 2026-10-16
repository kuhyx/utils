# sickdays

One shared pool of **sick days** that every gate respects.

Every day is a normal day until it is marked sick. There is no cap, no
budget, no reason to give and no countdown. The one rule is the calendar:
only today or a later day can be marked or un-marked — never a past one.

This replaces screen-locker's capped sick day (rolling windows, 120-character
justifications). It is **not** the free-day pool: `freedays` is a separate
pool with its own file and remote node, and a date is never in both.

## For a gate app

```python
import sickdays

if sickdays.is_sick_day(today):   # default: today
    ...  # apply this gate's sick-day rules
```

`is_sick_day()` reads one local JSON file, never the network, and **never
raises**. A missing file means "no sick days". An unreadable or corrupt file
is logged as a warning and also reads as *not sick*: it fails closed, so the
alarm rings and the locks apply.

## For a person

```console
$ sickdays add                  # today
$ sickdays add 2026-10-20       # or 'tomorrow'
$ sickdays remove 2026-10-20    # today or later only
$ sickdays list                 # every sick day, oldest first
$ sickdays check tomorrow       # exit 0 if sick, 1 if not -- for scripts
$ sickdays sync                 # pull and push now
```

`python -m sickdays ...` is the same command. Exit codes: `0` done, `1`
refused (past day, already sick, not sick, a free day, sync unavailable),
`2` input not understood.

## API

| call | does |
|---|---|
| `is_sick_day(day=None, *, log_path=None, now=None) -> bool` | the gate question; never raises |
| `sick_days(*, log_path=None) -> frozenset[date]` | every date currently sick |
| `add_sick_day(day, *, is_free=None, paths=None, now=None) -> SickDay` | today or later; refuses a free day |
| `remove_sick_day(day, *, paths=None, now=None) -> SickDay` | today or later |
| `import_legacy(days, *, paths=None) -> list[date]` | migration only: may write past dates; idempotent |
| `ensure_not_sick(day, *, paths=None)` | for freedays' callers, before `freedays.mark` |
| `sync()`, `sync_quietly()` | one pull/merge/push tick |

Refusals subclass `SickDayError`: `PastDateError`, `AlreadySickError`,
`NotSickError`, `FreeDayConflictError`, `SickDayConflictError`,
`ConflictCheckUnavailableError`, `UnreadablePoolError`. Writers refuse an
existing-but-corrupt pool (`UnreadablePoolError`) instead of overwriting it
with an empty one; `sync` reads it as empty, so a peer's copy restores it.

`import_legacy` is for screen-locker's `sick_history.json` (2026-06-21 and
2026-07-24, both before every gate start). It skips the free-day check.

## A date is never in both pools

Neither package imports the other at module level, so they can never form an
import cycle:

- **Adding a sick day** checks a predicate `is_free(day) -> bool`. By default
  `add_sick_day` imports `freedays` *lazily*, by name, at call time
  (`_conflict.free_day_predicate`). If freedays is not importable the add is
  **refused** (`ConflictCheckUnavailableError`). The invariant is hard, so
  "could not check" never counts as "not free". A phone port or a test passes
  its own `is_free`.
- **Marking a free day** is freedays' write. Its callers (CLIs, phone, lock
  screen) call `sickdays.ensure_not_sick(day)` first. That needs no freedays
  import at all. freedays itself does not check yet.

## Storage

| what | where |
|---|---|
| the pool | `~/.local/share/sickdays/sick_days.json` |
| device uuid (per install) | `~/.local/share/sickdays/device_id` |
| audit trail (HMAC-signed, append-only) | `~/.local/share/sickdays/audit.jsonl` + `hmac.key` |
| sync bookkeeping (local only) | `~/.local/share/sickdays/sync_state.json` |

Days are local calendar dates (`_day.today()`), the same as freedays.

## Sync and the wire format (for the phone)

Firebase RTDB only, shared credential `~/.config/crdt-sync/` (crdt-sync's
`firebase_client_for("sickdays")`). One directory per device; each device
writes only its own node:

| RTDB node | value |
|---|---|
| `sickdays-sync/devices/<uuid>/sick_days~2Ejson` | a JSON **string** holding the log (below) |
| `sickdays-sync/revs/<uuid>` | hex SHA-256 of that exact string |

The logical path is `sickdays-sync/devices/<uuid>/sick_days.json`. crdt-sync
escapes the `.` in keys as `~2E`. Write the log first, then the rev; a peer
skips any device whose rev it has already merged. The `<uuid>` is a
persisted per-install uuid4, never `pc`/`phone`.

The log is a JSON object keyed by ISO date. Each value is a crdt-sync record:

```json
{
  "2026-10-20": {
    "id": "2026-10-20",
    "fields": {
      "state": ["sick", "2026-10-16T08:12:03.517Z-0000-<uuid>"],
      "actor": ["<uuid>", "2026-10-16T08:12:03.517Z-0000-<uuid>"]
    },
    "deleted": false,
    "deleted_hlc": null
  }
}
```

- `id` equals the key: `YYYY-MM-DD`, local date.
- `state` is `"sick"` or `"cleared"`. Anything else, or a missing record,
  means a normal day. `actor` is the uuid of the device that last wrote it.
- Each field is `[value, hlc]`, and every field of one write carries the
  **same** HLC. The HLC string is
  `YYYY-MM-DDTHH:MM:SS.mmmZ-<counter, 4 hex>-<node uuid>` (UTC wall time). It
  orders as the tuple `(wall_ms, counter, node_id)`. A new tick is
  `max(now_ms, last_own.wall_ms)`, with the counter bumped when the wall time
  did not move.
- **Merge = per-field last-writer-wins**: for each date, keep the field with
  the greater HLC. So the latest add *or remove* of a date wins on every
  device, and a date can be added and removed any number of times.
- **Remove = write `state: "cleared"`. Never write `deleted: true`.**
  crdt-sync OR-merges tombstones, so a deleted date could never be marked
  sick again. A tombstoned record reads as "not sick".

Don't hand-roll this on Dart: use `crdt_sync_dart` (`syncLog`, `logToJson`
/ `logFromJson`), exactly as wake-alarm's `free_day_sync.dart` does for
`freedays-sync`. Only the prefix (`sickdays-sync/devices`), the filename
(`sick_days.json`) and the `"sick"` state value differ. There is no
`consumed` or `reason` field.

## Install

```console
$ ./install.sh             # own venv (crdt-sync + freedays + sickdays), CLI on PATH, 15-min sync timer
$ ./install.sh --no-timer
```

## Development

```console
$ pip install ../crdt-sync && pip install --no-deps ../freedays
$ pip install -r requirements.txt && pip install --no-deps -e .
$ python -m pytest              # 100% branch coverage is enforced
$ pre-commit run --config sickdays/.pre-commit-config.yaml --all-files   # from the repo root
```
