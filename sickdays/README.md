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

### Keeping some lockers on a sick day (0.2.0)

A sick day may **keep** some lockers active. A locker *stands down* on a day
iff the day is sick **and** the locker is not in that day's keep set. A gate
that is one of the lockers asks the narrower question:

```python
if sickdays.stands_down(sickdays.LOCKER_LEETCODE):   # default: today
    ...  # this locker is off today
```

Locker ids (`LOCKER_*` constants): `workout`, `leetcode`, `book`, `diet`,
`alarm`. `alarm` is one switch for the phone ring, the PC fallback ring, the
RTC self-wake and the missed-alarm penalty.

`LOCKERS` is all five, in that order. `stands_down` never raises for a data
problem (only `ValueError` for an id not in `LOCKERS`). Every doubt answers
"the locks apply": an unreadable pool is not sick, a malformed keep set keeps
every locker. `is_sick_day` is unchanged, so a gate still on the 0.1.0 API
keeps working and treats every sick day as "everything stands down".

## For a person

```console
$ sickdays add                  # today
$ sickdays add 2026-10-20       # or 'tomorrow'
$ sickdays add tomorrow --keep leetcode --keep workout   # those two stay on
$ sickdays keep 2026-10-20 diet # replace the kept set of a sick day
$ sickdays keep 2026-10-20      # keep nothing: every locker stands down again
$ sickdays remove 2026-10-20    # today or later only
$ sickdays list                 # every sick day, oldest first
2026-10-16  (today)
2026-10-20  keep: diet
$ sickdays check tomorrow       # exit 0 if sick, 1 if not -- for scripts
$ sickdays check --locker alarm # exit 0 iff that locker stands down today
$ sickdays sync                 # pull and push now
```

`python -m sickdays ...` is the same command. Exit codes: `0` done, `1`
refused (past day, already sick, not sick, a free day, sync unavailable),
`2` input not understood (a bad date, or a locker id not in `LOCKERS` --
`--keep`, `keep` and `--locker` only accept the five ids).

## The picker window (0.3.0)

`sickdays gui` (or the "Sick days" launcher): the phone's Sick days screen on
Tk -- calendar, a five-switch panel per day, the days ahead. Past days are
inert; a free day is refused; each write starts `sync_quietly()` on a
non-daemon thread. `WM_CLASS "sickdays", "Sickdays"`; `Escape` closes. Embed
just the panel (`import sickdays` never imports tkinter):

```python
from sickdays.gui import KeepPanel   # a plain tk.Frame: no root, grab or wm_* call
KeepPanel(parent, day, *, on_saved, on_cancel=None, paths=None).pack()
```

Normal day: five switches, all off (off = stands down), "Mark sick"; sick
day: its switches, "Save", "Clear sick day". Past/free/uncheckable days show
why and offer no write; a refusal (or a click mid-sync) shows in the panel.
`on_saved(SickDay | None)` fires after the write and sync start: the entry on
Mark sick / a changed Save (`is_sick=True`) or Clear (`is_sick=False`), `None`
on an unchanged Save (nothing written). The panel never destroys itself.

## API

| call | does |
|---|---|
| `is_sick_day(day=None, *, log_path=None, now=None) -> bool` | the gate question; never raises |
| `sick_days(*, log_path=None) -> frozenset[date]` | every date currently sick |
| `stands_down(locker, day=None, *, log_path=None, now=None) -> bool` | the per-locker gate question; never raises for data, `ValueError` for an unknown id |
| `kept_lockers(day=None, *, log_path=None, now=None) -> frozenset[str]` | the day's kept lockers; empty when not sick |
| `add_sick_day(day, *, keep=(), is_free=None, paths=None, now=None) -> SickDay` | today or later; refuses a free day; `ValueError` on an unknown locker |
| `set_kept_lockers(day, keep, *, paths=None, now=None) -> SickDay` | replace an existing sick day's kept set; today or later |
| `remove_sick_day(day, *, paths=None, now=None) -> SickDay` | today or later |
| `import_legacy(days, *, paths=None) -> list[date]` | migration only: may write past dates; idempotent |
| `ensure_not_sick(day, *, paths=None)` | for freedays' callers, before `freedays.mark` |
| `sync()`, `sync_quietly()` | one pull/merge/push tick |

`SickDay` is `(day, is_sick, actor="", keep=frozenset())`. The locker ids are
`LOCKER_WORKOUT`, `LOCKER_LEETCODE`, `LOCKER_BOOK`, `LOCKER_DIET`,
`LOCKER_ALARM` and the tuple `LOCKERS`.

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
| audit trail (HMAC-signed, append-only; actions `add`, `remove`, `keep`, `import`) | `~/.local/share/sickdays/audit.jsonl` + `hmac.key` |
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
      "actor": ["<uuid>", "2026-10-16T08:12:03.517Z-0000-<uuid>"],
      "keep": [["leetcode", "workout"], "2026-10-16T08:12:03.517Z-0000-<uuid>"]
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

#### `keep` (0.2.0)

`keep` is `[<list of locker-id strings>, <hlc>]`. The list is **sorted**
(plain string order) and **de-duplicated**, always: the rev is a SHA-256 of
the exact JSON string, so two devices holding the same set must write the
same bytes. Ids: `workout`, `leetcode`, `book`, `diet`, `alarm`.

Writing:

- **add** (mark sick) writes `state: "sick"`, `actor` and `keep` (default
  `[]`), all three with the **same** HLC tick, always. So a stale `keep` from
  another device cannot survive a clear and a re-add.
- **remove** writes `state: "cleared"`, `actor` and `keep: []`, same tick.
- **change kept lockers** on an existing sick day **does not touch `state`**:
  copy the record, stamp only `keep` and `actor` with one fresh tick, and
  leave `state` (and its HLC) as it was. Re-stamping `state` would make a
  keep edit re-assert "sick" over a concurrent clear. Only today or later,
  only on a day that is currently sick.
- Every new tick is issued after both this device's last tick and the
  greatest HLC already on that day's record, so an edit never comes out
  older than the `state` it was made against.

Reading (a locker *stands down* iff the day is sick and the locker is not in
the keep set), checked in this order:

1. Day not sick (no record, tombstone, state not `"sick"`, unreadable pool)
   -> nothing stands down; `keep` is not looked at.
2. No `keep` field (every 0.1.0 record) -> keep nothing: every locker stands
   down.
3. `keep`'s HLC is **older** than `state`'s HLC -> stale (an old 0.1.0
   client re-added the day) -> keep nothing. Equal HLCs are not stale.
4. `keep`'s value is not a list, or holds a non-string element -> malformed
   -> fail closed: **every** locker is kept (nothing stands down), and a
   warning is logged. (A stale malformed value is just stale: rule 3 wins.)
5. Otherwise the kept set is the list, with unknown string ids **ignored**
   (forward compatibility), not an error.

Don't hand-roll this on Dart: use `crdt_sync_dart` (`syncLog`, `logToJson`
/ `logFromJson`), exactly as wake-alarm's `free_day_sync.dart` does for
`freedays-sync`. Only the prefix (`sickdays-sync/devices`), the filename
(`sick_days.json`) and the `"sick"` state value differ. There is no
`consumed` or `reason` field. The phone must follow the `keep` rules above.

## Install

```console
$ ./install.sh             # own venv (crdt-sync + freedays + sickdays), CLI on PATH, launcher, 15-min sync timer
$ ./install.sh --no-timer
```

## Development

```console
$ pip install ../crdt-sync && pip install --no-deps ../freedays
$ pip install -r requirements.txt && pip install --no-deps -e .
$ xvfb-run -a python -m pytest  # 100% branch coverage; the GUI tests need a display
$ pre-commit run --config sickdays/.pre-commit-config.yaml --all-files   # from the repo root
```
