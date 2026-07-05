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

Pin to a tag once this is pushed:

```yaml
dependencies:
  crdt_sync:
    git:
      url: https://github.com/kuhyx/crdt_sync_dart
      ref: v0.1.0
```

## Usage

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

## Development

```bash
dart pub get
dart analyze
dart test
```
