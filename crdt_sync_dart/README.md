# crdt_sync

Shared CRDT merge scheme + GitHub-Contents-API sync transport, extracted for
reuse across four personal apps that each need cross-device sync: `todo`,
`diet_guard`'s Flutter app, `wake_alarm`'s `phone_app`, and screen-locker's
`workout_app`. Pure Dart -- no Flutter SDK dependency (`package:http` only)
-- so it works in both Flutter apps and plain Dart tooling. Mirrors the
[Python `crdt-sync`](https://github.com/kuhyx/crdt-sync) package
module-for-module and test-for-test, so the merge algorithm canonically
agrees on both sides of any sync between a Dart client and a Python one.

## The merge scheme

See the Python package's README for the full rationale; in short, a generic
**LWW-map-with-sticky-remove**:

- `Hlc` -- a Hybrid Logical Clock `(wallTimeMs, counter, nodeId)`, totally
  ordered, monotonic even across clock skew.
- `Record` -- an id, a per-field last-writer-wins map (`fieldName ->
  (value, Hlc)`), and a sticky `deleted` flag (`deleted = a.deleted ||
  b.deleted`, never the other way -- a delete can never be silently undone).
- `Log` -- `Map<String, Record>`, merged by taking the union of ids and
  merging shared ones.

All three merges are commutative and idempotent -- see `test/log_test.dart`
for the concrete convergence-property tests.

## Install

Consume via a git dependency on the `utils` monorepo:

```yaml
dependencies:
  crdt_sync:
    git:
      url: https://github.com/kuhyx/utils
      ref: crdt_sync_dart-v0.11.0
      path: crdt_sync_dart
```

## Usage

The example below uses the **GitHub** transport, which is now the mirror
rather than the primary — see [Firebase transport](#firebase-transport-the-current-one)
for what a new consumer should use. The merge scheme itself is transport-agnostic:
`syncLog` takes any `RemoteStore`.

```dart
import 'package:crdt_sync/crdt_sync.dart';

final nodeId = 'phone';
final clock = Hlc.newTick(nodeId);
final record = Record(
  id: 'abc123',
  fields: {'text': ('buy milk', clock)},
);

final client = GitHubClient(owner: 'kuhyx', repo: 'my-app-sync', token: token);
final merged = await syncLog(
  client: client,
  deviceId: nodeId,
  pathPrefix: 'devices',
  localLog: {record.id: record},
  encode: (log) => jsonEncode(log.map((k, r) => MapEntry(k, r.toJson()))),
  decode: (text) => (jsonDecode(text) as Map<String, dynamic>).map(
    (k, v) => MapEntry(k, Record.fromJson(v as Map<String, dynamic>)),
  ),
);
```

`syncLog` pulls every other device's last-pushed log from
`<pathPrefix>/<other-device-id>/...`, merges each into the local log with
`mergeLogs`, then pushes this device's own merged result back up.

## Firebase transport (the current one)

**If you are adding sync to a new Flutter app, use
[`crdt_sync_flutter`](../crdt_sync_flutter) and stop reading here.** It wraps
everything below in one call. The rest of this section is what that package is
built on, and what a non-Flutter consumer (a CLI tool, a systemd job) uses
directly.

The `GitHubClient` shown above is the **original** transport and is now a
mirror. The primary is Firebase Realtime Database over plain REST:

```dart
final client = await firebaseClientFor(
  config: kProject.configFor(email),
  store: credentialStore,        // where the refresh token lives
  password: password,            // or googleIdToken, on a fresh install
  expectedUid: kSyncUid,
);
final merged = await syncLog(client: client, /* ... as above ... */);
```

**Plain REST, not FlutterFire, deliberately.** The official `firebase_auth`
and `firebase_database` plugins have no Linux desktop support, and one
consumer runs headless under systemd. The REST endpoints are ordinary HTTPS
and behave identically on Android, Linux and headless. RTDB rather than
Firestore because the Spark plan bills only storage and bandwidth, with no
per-operation quota that a misbehaving sync loop could exhaust.

What the pieces are:

| Type | Role |
|---|---|
| `FirebaseProject` | `apiKey` + `databaseUrl`. Safe to commit. |
| `FirebaseAccount` | `email` + `password`. Never commit; keystore only. |
| `FirebaseCredentials` | The refresh token and its expiry. |
| `FirebaseCredentialStore` | Where that token is persisted. |
| `SecureCredentialStore` | A store over three injected closures. |
| `FirebaseTokenProvider` | Signs in and refreshes; 5-minute skew. |
| `FirebaseRestClient` | The `RemoteStore` itself. |
| `MirrorStore` | Firebase primary + GitHub mirror, during a cutover. |

The public/private split is not cosmetic: every repo in this fleet is public.
`apiKey` and `databaseUrl` identify the *project* and already ship inside every
APK — the security rules, not secrecy, protect the data. The account email and
password identify *a person* and are entered once per device.

### `password: ''` is legal

The Google one-tap path and the seeded-session path both store an empty
password, because on those devices the refresh token *is* the credential.
`FirebaseAccount.tryParse` used to reject that blob, so such a device wrote an
account marker it could never read back and reported "not configured" on every
later launch. Fixed in **v0.11.0**; callers guard `password.isEmpty` and pass
null, meaning "no password on this device".

## Local persistence (`LogStore`)

The merge scheme above is in-memory only. For an app that needs to keep its
`Log` on disk and drive a live UI off it, this package also ships a
domain-agnostic `LogStore`:

```dart
import 'package:crdt_sync/crdt_sync.dart';
import 'package:crdt_sync/crdt_sync_io.dart'; // FileLogPersistence (dart:io)

final store = LogStore(
  persistence: FileLogPersistence(File('$docsDir/notes.json')),
  nodeId: 'phone',
);
await store.load();

// Reactive read: re-derive a domain view whenever anything changes. Filtering,
// sorting and search live here, in the app -- the store is field-agnostic.
final Stream<List<Record>> visible = store.changes.map(
  (_) => store.values.where((r) => !r.deleted).toList(),
);

await store.upsert(Record(id: 'n1', fields: {'text': ('hi', store.nextHlc())}));
await store.delete('n1'); // sticky tombstone, not a hard remove

// After a sync tick, swap in the merged result:
await store.replaceAll(await syncLog(/* ... */, localLog: store.snapshot()));
```

`LogStore` is pure Dart (import it from the main barrel); the filesystem-backed
`FileLogPersistence` lives behind the separate `crdt_sync_io.dart` entrypoint so
the core stays web-safe. Querying is deliberately **not** in the library — a
`Record`'s fields are an opaque map, so the app filters `store.values` itself.
The Python side mirrors the on-disk format via `crdt_sync.dump_log`/`read_log`
(load/save only; no reactive stream — that's a Dart/Flutter convenience).

## Development

```bash
dart pub get
dart analyze
dart test
```
