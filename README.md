# utils

Shared libraries used across kuhyx's other projects. Each subdirectory is a
formerly-standalone repo, folded in here with full commit history preserved
(see each subdirectory's own `git log` for its pre-merge history).

## crdt_sync_dart/

Dart/Flutter CRDT sync library (pub package name: `crdt_sync`, not published
to pub.dev — consumed via a git dependency). Mirrors `crdt-sync` (below)
module-for-module and test-for-test. Consumed by `diet_guard`'s app,
screen-locker's `workout_app`, `wake_alarm`'s `phone_app`, and `todo` (whose
notes are stored in the v0.2.0 `LogStore`).

Consume via:
```yaml
dependencies:
  crdt_sync:
    git:
      url: https://github.com/kuhyx/utils
      ref: crdt_sync_dart-v0.2.0
      path: crdt_sync_dart
```

## crdt-sync/

Python CRDT sync library (package: `crdt_sync`, not published to PyPI). Same
design as `crdt_sync_dart` (HLC clocks, per-field LWW, sticky-delete
tombstones). Consumed by `diet-guard` and `screen-locker`.

Consume via:
```
crdt-sync @ git+https://github.com/kuhyx/utils@crdt-sync-v0.2.0#subdirectory=crdt-sync
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

## unified-design-system/

Not a package — the frozen design tokens (colors, spacing, type, radius,
shadow policy) and per-stack (Flutter/web/Tkinter) implementation patterns
that keep every one of kuhy's repos visually identical, plus annotated
component references (`components.html`, `button.html`). Read
[`unified-design-system/README.md`](unified-design-system/README.md) and
`tokens.md` before touching any theme/CSS/style file in any repo. The
`unified-design-system` Claude Code skill is a thin pointer here, not a
duplicate.
