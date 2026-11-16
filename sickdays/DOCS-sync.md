# sickdays: sync and the wire format (for the phone)

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
`consumed` or `reason` field. The phone must follow the `keep` rules in [README.md](README.md).
