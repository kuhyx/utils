# crdt-sync

Shared CRDT merge scheme + GitHub-Contents-API sync transport, extracted for
reuse across four personal apps that each need cross-device sync:
[todo](https://github.com/kuhyx/todo-app),
[diet_guard](https://github.com/kuhyx/testsAndMisc/tree/main/python_pkg/diet_guard),
[wake_alarm](https://github.com/kuhyx/testsAndMisc/tree/main/python_pkg/wake_alarm),
and [screen-locker](https://github.com/kuhyx/screen-locker).

## Why

Two of those apps (diet_guard, and independently todo) had already converged
on the same shape of solution: treat a private GitHub repo as dumb file
storage via the REST Contents API (not a git clone), have each device push
its own file, and merge on read. diet_guard's merge logic
(entry-id-keyed, tombstone-wins) and todo's merge logic (`sqlite_crdt`'s
per-field HLC last-writer-wins) solve the same underlying problem —
convergent merge without a central server — for two different data shapes
(append-only logs vs. mutable per-field records). `crdt-sync` generalizes
both into one scheme so all four apps can share it, at the cost of todo's
notes and wake_alarm's single wake-time value both running through
CRDT machinery their own data doesn't strictly need — an explicit
consistency-over-leanness tradeoff.

## The merge scheme

A generic **LWW-map-with-sticky-remove**, built from three pieces:

- **`Hlc`** — a Hybrid Logical Clock: `(wall_time_ms, counter, node_id)`,
  totally ordered by tuple comparison (`node_id` breaks ties between two
  clocks with identical wall time and counter, so no two distinct devices'
  clocks ever compare equal). `Hlc.new_tick(node_id, previous)` advances off
  wall-clock time, or bumps `counter` when the wall clock hasn't moved past
  `previous` — the standard HLC construction, guaranteeing monotonicity even
  across clock skew or two ticks in the same millisecond.
- **`Record`** — `id`, a `fields` map of `name -> (value, Hlc)`, and a sticky
  `deleted` flag. `merge_field` keeps whichever side's `Hlc` is greater,
  per field — this is what lets two devices concurrently edit *different*
  fields of the same record (or the same field) and converge deterministically
  without a central authority. `merge_record`'s `deleted` is **not** itself
  per-field LWW: it's `a.deleted or b.deleted`, monotonic and one-directional.
  This preserves a guarantee diet_guard's original tombstone scheme already
  relied on — a delete can never be silently undone by merging in an older
  non-deleted copy pulled from a device that hasn't seen the delete yet.
- **`Log`** = `dict[id, Record]`. `merge_logs` takes the union of ids and
  `merge_record`s the ones present on both sides.

All three merges are commutative and idempotent (provable directly from
`max`-by-`Hlc` and boolean-`or`), so pull order between devices never matters
and a repeated sync tick is a no-op — see `crdt_sync/tests/test_log.py`'s
property-style cases for the concrete proof.

**Per-app adapters are out of scope for this library.** Translating a `Note`,
a `FoodEntry`, a workout entry, or wake_alarm's `{hour, minute}` value to and
from `Record` is each app's own job — keeping this library domain-agnostic is
what makes it actually shared, rather than shaped around one app's schema.

## Install

```bash
pip install "crdt-sync @ git+https://github.com/kuhyx/crdt-sync@v0.1.0"
```

## Usage

```python
from crdt_sync import GitHubSyncClient, Hlc, Record, sync_log

node_id = "pc"
clock = Hlc.new_tick(node_id)
record = Record(id="abc123", fields={"text": ("buy milk", clock)}, deleted=False)

client = GitHubSyncClient(owner="kuhyx", repo="my-app-sync", token=token)
result = sync_log(
    client=client,
    device_id=node_id,
    path_prefix="devices",
    local_log={record.id: record},
    encode=lambda log: json.dumps({k: r.to_dict() for k, r in log.items()}),
    decode=lambda text: {
        k: Record.from_dict(v) for k, v in json.loads(text).items()
    },
)
```

`sync_log` pulls every other device's last-pushed log from
`<path_prefix>/<other-device-id>/...`, merges each into the local log with
`merge_logs`, then pushes this device's own merged result back up — the same
pull-all/merge/push-own pattern diet_guard's `_sync.py` already used, made
domain-agnostic via the `encode`/`decode` callbacks so callers keep their own
on-disk JSON shape instead of `crdt-sync` dictating one.

## Local persistence

For persisting a `Log` to disk, `crdt_sync` ships load/save helpers that share
a canonical on-disk JSON shape with the Dart `crdt_sync_dart.LogStore`, so a log
written by one language parses in the other:

```python
from crdt_sync import dump_log, load_log, read_log, write_log

write_log(path, log)          # atomic temp-file-then-rename
log = read_log(path)          # empty on a missing or corrupt file
text = dump_log(log)          # -> canonical JSON string
log = load_log(text)          # <- parse it back
```

These are load/save only. The Dart side additionally offers a *reactive*
`LogStore` (a change stream to drive a live UI); that's a Flutter-only
convenience and has no Python equivalent by design — Python consumers here are
headless sync ticks.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest
pre-commit install && pre-commit install --hook-type pre-push
```
