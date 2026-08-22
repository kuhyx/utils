# sync_settings_ui

The shared **Sync settings** screen: Firebase sign-in (email/password or
Google one-tap), Disconnect, a live status line, and an optional Backup
section. Reused across every one of kuhy's Flutter apps that syncs, so the
screen behaves identically everywhere and is fixed in one place.

Generalized from the near-identical `_connectFirebase` / `_connectGoogle` /
`_disconnectFirebase` / `_load` logic that had been duplicated into every
app's settings screen.

## Install

```yaml
dependencies:
  sync_settings_ui:
    git:
      url: https://github.com/kuhyx/utils
      ref: sync_settings_ui-v0.1.0
      path: sync_settings_ui
```

## Usage

This package **never touches `flutter_secure_storage` or `google_sign_in`
itself** — every keystore read/write and every platform sign-in arrives as an
already-built closure. [`crdt_sync_flutter`](../crdt_sync_flutter) provides
all of them, so the two fit together directly:

```dart
import 'package:crdt_sync_flutter/crdt_sync_flutter.dart';
import 'package:sync_settings_ui/sync_settings_ui.dart';

SyncSettingsScreen(
  accountLoader: () => loadAccount(),
  accountSaver: saveAccount,
  accountClearer: clearAccount,
  sessionProbe: () => isSyncConfigured(kApp),
  firebaseFactory: () => openSync(kApp),
  googleFirebaseFactory: () => signInWithGoogle(
    kApp,
    tokenFetcher: googleIdToken, // the app's own google_sign_in call
  ),
  googleAvailable: googleSignInSupported,
  backup: BackupSlot(label: 'notes', export: _export, import: _import),
)
```

Pass `backup: null` to omit the Backup section entirely.

## What it gets right, so you don't re-derive it

**"Connected" means the session probe says so** — never that a factory
returned a non-null client. `FirebaseSyncController` returns a
`FirebaseConnectResult` carrying a six-case outcome:

| Outcome | Meaning |
|---|---|
| `connected` | Signed in, and the probe confirms a live session. |
| `rejected` | The credentials were refused. |
| `cancelled` | The user dismissed the picker. |
| `signedInButNotPersisted` | Sign-in worked; nothing durable was stored. |
| `wrongAccount` | Authenticated as a uid the rules do not allow. |
| `failed` | Anything else. |

`signedInButNotPersisted` and `wrongAccount` exist because both looked
identical to success from the call site and both produced a device that
appeared connected and synced nothing.

**The Google button is double-gated** on `supportsGoogle && googleAvailable`,
so a button that cannot possibly succeed is never rendered — a visible control
that always reports "cancelled" is worse than no control.

## Development

```bash
flutter pub get
flutter analyze
flutter test
```
