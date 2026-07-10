# utils

Shared libraries used across kuhyx's other projects. Each subdirectory is a
formerly-standalone repo, folded in here with full commit history preserved
(see each subdirectory's own `git log` for its pre-merge history).

## crdt_sync_dart/

Dart/Flutter CRDT sync library (pub package name: `crdt_sync`, not published
to pub.dev — consumed via a git dependency). Mirrors `crdt-sync` (below)
module-for-module and test-for-test. Not yet consumed by any app; planned
for screen-locker's workout sync.

Consume via:
```yaml
dependencies:
  crdt_sync:
    git:
      url: https://github.com/kuhyx/utils
      ref: crdt_sync_dart-v0.1.0
      path: crdt_sync_dart
```

## crdt-sync/

Python CRDT sync library (package: `crdt_sync`, not published to PyPI). Same
design as `crdt_sync_dart` (HLC clocks, per-field LWW, sticky-delete
tombstones). Not yet consumed by any app.

Consume via:
```
crdt-sync @ git+https://github.com/kuhyx/utils@crdt-sync-v0.1.0#subdirectory=crdt-sync
```

## guard-lib/

Bash tamper-resistance primitives (`guardctl`: chattr + bind-mount + systemd
watcher + pacman hooks). Not a package — installed by running
`guard-lib/install.sh` as root, which copies files onto the system
(`/usr/local/bin`, `/usr/local/lib/guard-lib`, systemd units, pacman hooks).
Consumed by `steam-backlog-enforcer` (expects a `guard-lib/install.sh`
sibling clone) and referenced by `screen-locker`.

## gatelock/

Python lock-window + HMAC log-integrity backend (package: `gatelock`, not
published to PyPI). Consumed via pip by `screen-locker`, `diet-guard`, and
`wake-alarm`:

```
gatelock @ git+https://github.com/kuhyx/utils@gatelock-v0.1.0#subdirectory=gatelock
```
