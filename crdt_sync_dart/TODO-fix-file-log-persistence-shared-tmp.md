# Make FileLogPersistence.write safe under concurrent calls

## what
`FileLogPersistence.write` (lib/src/io_store.dart) writes to a tmp file named
`<file>.<pid>.tmp` and renames it over the target. The name is per process,
not per call, so two overlapping writes in one process (per-keystroke upserts
in the todo app) share one tmp path: the first rename moves it away and the
second throws an unhandled `PathNotFoundException` on
`rename` of `todo_notes.json.<pid>.tmp`. Seen in the todo app during
concurrent per-keystroke upserts.
Fix by serializing writes (a chained Future per instance, last write wins)
or by using a unique tmp name per call; keep the atomic rename.

## done
A regression test in test/ fires 50 overlapping `write()` calls on one
instance, all complete without error, and the file then holds the text of a
call that was issued (not a torn mix). `dart test` in this package exits 0
with coverage still 100%.

## verify
`cd ~/src/utils/crdt_sync_dart && dart test --coverage=coverage`; then bump
the todo app's `crdt_sync` ref and run its full suite.

## read first
- lib/src/io_store.dart

REMOVE ME AFTER FINISH
