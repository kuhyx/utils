# crdt_sync_flutter

The Flutter half of [`crdt_sync`](../crdt_sync_dart). Adds the OS-keystore
adapter, a persisted per-install device id, the account store and a one-call
bootstrap, so a new app reaches "syncing" without writing any of it.

## Why this exists

`crdt_sync` is pure Dart on purpose — it runs from command-line tools and from
`wake_alarm`'s headless systemd job, so it cannot depend on
`flutter_secure_storage` or `google_sign_in`. It takes closures instead.

Every Flutter app then wrote the same ~390 lines to supply those closures
(`firebase_backend.dart` + `google_sign_in_backend.dart` + `google_platform*`),
and five apps ended up carrying near-identical copies. They then **drifted**:
`todo` gained an opt-out flag and a seeded-session path that `home_inventory`
and `wake_alarm` never received, so the same bug was fixed in one copy and
left live in the others.

This package owns that glue once.

## Install

```yaml
dependencies:
  crdt_sync_flutter:
    git:
      url: https://github.com/kuhyx/utils
      ref: crdt_sync_flutter-v0.1.1
      path: crdt_sync_flutter
```

It depends on `crdt_sync` itself, so you do not need to list both unless you
use the merge primitives (`Hlc`, `Record`, `LogStore`) directly — which most
apps do.

## Adding sync to a new app

**One const and one call.**

```dart
import 'package:crdt_sync_flutter/crdt_sync_flutter.dart';

/// The shared `kuhy-syncs` project. Safe to commit: the Web API key is a
/// public identifier that already ships inside every APK, and the security
/// rules -- not its secrecy -- are what protect the data.
const kApp = SyncApp(
  project: FirebaseProject(
    apiKey: 'AIzaSyCF_sA3xCMehAYXK8eND-rAygb9NXXW_8E',
    databaseUrl:
        'https://kuhy-syncs-default-rtdb.europe-west1.firebasedatabase.app',
  ),
  expectedUid: 'OvA2REQyLIhAHOEjzwS1o877rgG3',
);

// At a sync tick:
final client = await openSync(kApp);
if (client != null) {
  // ... syncLog(client: client, deviceId: identity.deviceId, ...)
  client.close();
}
```

`openSync` returns **null when this device is not set up**, which is a normal
state and not an error — the app keeps working against its local store and
simply does not sync.

For the device id:

```dart
final identity = await loadDeviceIdentity();
// identity.deviceId -- a per-install uuid under `crdt.nodeId`
```

The key matches what the existing apps already wrote, so an app adopting this
package keeps its identity rather than appearing as a brand-new device and
re-merging its own history as a stranger's. An app migrating off a role
constant passes `legacyId: 'phone'` so skip-own-writes stays correct.

### `databaseUrl` must be the regional host

The plain `*.firebaseio.com` form answers 404 with a `correctUrl` body rather
than an obvious error, so a wrong value reads like an auth failure and wastes
a debugging session.

### `expectedUid` is load-bearing

`signInWithIdp` signs in **or signs up**. An unlinked Google account is
accepted as a new uid, authenticates fine, and is then denied every read and
write — a sync that silently never syncs. `expectedUid` catches it at
sign-in instead.

## Signing in

There is no way to make a fresh install sync with zero interaction, and that
is deliberate: these repos are public, so the account's email and password
cannot be committed. The best achievable is **install → sign in once →
syncing forever**, and the refresh token then lives in the OS keystore.

Use [`sync_settings_ui`](../sync_settings_ui) for that screen rather than
building one; it takes the closures this package provides:

```dart
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
)
```

`signInWithGoogle` is the interactive path and takes the token fetcher as a
closure — `google_sign_in` is Android/iOS/web only, and this package must keep
working on Linux desktop.

**`openSync` deliberately never offers Google.** It runs from background ticks
and, in some apps, before `runApp`; offering Google there would raise the OS
account picker with no user action behind it.

## Desktop provisioning

An app whose desktop build is the web build behind a local wrapper can let
that wrapper hand over a seeded session, so the account is not retyped per
machine:

```dart
const kApp = SyncApp(
  project: ...,
  expectedUid: ...,
  routes: WrapperRoutes(
    credentialsPath: '/sync-credentials',
    accountPath: '/sync-account', // optional legacy fallback
  ),
);
```

`routes` is per-app because each wrapper serves its own seeded file (the
`todo` app's is `~/.config/todo/firebase_auth.json`, written by
`seed_session.py`). Pass nothing and the whole fallback is skipped — which is
what Android does in practice, since `Uri.base` there is `file:///`.

Nothing in this package reads `~/.config/crdt-sync/` directly. That is the
desktop/Python half, reached over the wrapper's HTTP routes.

## Testing

The keystore fake ships with the package, so a consuming app does not rebuild
it:

```dart
import 'package:crdt_sync_flutter/testing/fake_secure_storage.dart';

installFakeSecureStorage(); // auto-removes on tear down
installFakeSecureStorage(throwing: true); // a host with no secret service
```

Nothing in this package's own suite reaches the network or a real keystore.

```bash
flutter test --coverage   # 35 tests, 100% line coverage
flutter analyze
```

## Not yet migrated

`todo`, `home_inventory`, `diet_guard`, `workout_app` and `wake_alarm` still
carry their own copies and stay pinned to `crdt_sync_dart-v0.10.0`. That is
deliberate — those fallbacks are load-bearing and the migration is forward-only
— but it means **a fix made here does not reach them**. Converging them is a
separate task; see the drift note above for what each copy is missing.
