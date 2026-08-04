import 'dart:convert';

import 'package:crypto/crypto.dart';

import 'log.dart';
import 'record.dart';
import 'remote_store.dart';
import 'store.dart';

const _defaultFilename = 'log.json';

/// What one device remembers between ticks so it can skip needless traffic.
///
/// Two facts, both cheap:
/// * [pushedRev] -- the hash of what this device last pushed, so an unchanged
///   log is not re-uploaded. 88% of the pushes in the GitHub-backed history
///   were byte-identical no-ops.
/// * [peerRevs] -- the hash each peer had last time we downloaded it, so an
///   unchanged peer is not re-downloaded.
///
/// **Must be stored next to the log itself and cleared with it.** Skipping an
/// unchanged peer is only sound because that peer's records are already
/// merged into the local log; a cache that outlived its log would skip peers
/// whose data had been lost.
class SyncState {
  const SyncState({this.pushedRev, this.peerRevs = const {}});

  factory SyncState.fromJson(Map<String, dynamic> json) => SyncState(
    pushedRev: json['pushed_rev'] as String?,
    peerRevs: {
      for (final entry
          in (json['peer_revs'] as Map<String, dynamic>? ?? {}).entries)
        if (entry.value is String) entry.key: entry.value as String,
    },
  );

  final String? pushedRev;
  final Map<String, String> peerRevs;

  Map<String, dynamic> toJson() => {
    'pushed_rev': pushedRev,
    'peer_revs': peerRevs,
  };
}

/// Where [syncLog] persists its [SyncState] between runs.
///
/// Persistence is what makes the saving real for the short-lived callers:
/// `wake_alarm` PC is a fresh process every minute and `diet_guard` PC a
/// fresh process every 15 minutes, so an in-memory cache would save nothing.
abstract interface class SyncStateStore {
  Future<SyncState> load();
  Future<void> save(SyncState state);
}

/// A [SyncStateStore] that forgets everything, for tests and one-shot runs.
///
/// Correct but pessimistic: every tick re-downloads every peer and re-pushes
/// the local log, which is exactly the old behaviour.
class InMemorySyncStateStore implements SyncStateStore {
  SyncState _state = const SyncState();

  @override
  Future<SyncState> load() async => _state;

  @override
  Future<void> save(SyncState state) async => _state = state;
}

/// A [SyncStateStore] that persists through a [LogPersistence] port.
///
/// This is the mobile counterpart to Python's `FileSyncStateStore`, and it is
/// what makes the revision saving real on a phone: an app is a fresh process
/// after every cold start, so an [InMemorySyncStateStore] would forget every
/// peer revision and re-download all of them on each launch -- the exact
/// traffic the revision scheme exists to avoid.
///
/// Takes the pure-Dart [LogPersistence] port rather than a `File` so it works
/// on web (where `dart:io` is unavailable) and is trivially faked in tests.
/// On mobile and desktop, pass a `FileLogPersistence` from
/// `package:crdt_sync/crdt_sync_io.dart`, which already writes atomically.
///
/// **Store this next to the log it describes and clear the two together.**
/// Skipping an unchanged peer is only sound because that peer's records are
/// already merged into the local log; state that outlived its log would skip
/// peers whose data had been lost. See [SyncState].
class PersistedSyncStateStore implements SyncStateStore {
  /// Persists state through [persistence].
  PersistedSyncStateStore(this._persistence);

  final LogPersistence _persistence;

  /// Returns the stored state, or a default one if absent or unreadable.
  ///
  /// A corrupt or half-written file degrades to "remember nothing", which
  /// costs one tick of extra traffic rather than failing the sync -- the same
  /// fail-safe choice the Python side makes.
  @override
  Future<SyncState> load() async {
    final String? text;
    try {
      text = await _persistence.read();
    } on Exception {
      return const SyncState();
    }
    if (text == null || text.isEmpty) return const SyncState();
    try {
      final decoded = jsonDecode(text);
      if (decoded is! Map<String, dynamic>) return const SyncState();
      return SyncState.fromJson(decoded);
    } on FormatException {
      return const SyncState();
    }
  }

  @override
  Future<void> save(SyncState state) async =>
      _persistence.write(jsonEncode(state.toJson()));
}

/// The revision of a serialized log: a content hash, not a clock reading.
///
/// A hash rather than the log's maximum HLC because merging a peer's *older*
/// record changes the content without raising the maximum -- with three
/// devices in one namespace (diet-guard has `pc`, `phone` and `desktop`) a
/// clock-based revision can miss a peer's merged state. It is also the same
/// value used to suppress no-op pushes, so the two optimisations share one
/// mechanism.
String revisionOf(String encodedLog) =>
    sha256.convert(utf8.encode(encodedLog)).toString();

/// Runs one full sync tick: pull every other device's log, merge, push.
///
/// Pulls from `<pathPrefix>/<other-device-id>/<filename>` for every device
/// directory the remote reports under [pathPrefix], merges each into
/// [localLog] with [mergeLogs], then pushes this device's own merged result
/// to `<pathPrefix>/<deviceId>/<filename>`.
///
/// [encode] serializes a merged log for pushing. [decode] parses a remote
/// device's pushed text back into a log; throwing [FormatException] (bad
/// JSON syntax) or [TypeError] (valid JSON, wrong shape -- e.g. a missing
/// or mistyped field during [Record.fromJson]) is treated as a
/// corrupt/unparsable push, and that device is skipped for this tick
/// rather than aborting the whole sync. Mirrors the Python `sync_log`'s
/// `(ValueError, KeyError, TypeError)` catch for the same reason.
///
/// Pass [stateStore] to enable revision tracking, which skips downloading
/// peers that have not changed and skips pushing a log that has not changed.
/// Without it the tick behaves exactly as it always did: fetch everything,
/// push unconditionally.
///
/// Revisions live at `<revsPath>/<deviceId>` -- one small text node per
/// device, each written only by its owner. Deliberately *not* one shared map
/// per namespace: a whole-map write would erase every other device's entry,
/// after which those peers would look permanently unchanged and never be
/// fetched again. Per-device keys make that failure impossible rather than
/// merely avoided.
Future<Log> syncLog({
  required RemoteStore client,
  required String deviceId,
  required String pathPrefix,
  required Log localLog,
  required String Function(Log log) encode,
  required Log Function(String text) decode,
  String filename = _defaultFilename,
  String commitMessage = 'crdt_sync: update log',
  SyncStateStore? stateStore,
  String? revsPath,
}) async {
  final revs = revsPath ?? defaultRevsPath(pathPrefix);
  final state = await stateStore?.load() ?? const SyncState();
  final remoteRevs = stateStore == null
      ? const <String, String>{}
      : await _remoteRevs(client, revs);

  var mergedLog = Map<String, Record>.from(localLog);
  final seenRevs = <String, String>{};
  for (final otherDeviceId in await client.listDirectory(pathPrefix)) {
    if (otherDeviceId == deviceId) continue;
    final remoteRev = remoteRevs[otherDeviceId];
    if (remoteRev != null && remoteRev == state.peerRevs[otherDeviceId]) {
      // Unchanged since we last merged it, and that merge is already part of
      // localLog -- so the (potentially hundreds of KB) download is pure
      // waste. Carry the revision forward so it stays skipped next tick.
      seenRevs[otherDeviceId] = remoteRev;
      continue;
    }
    final text = await client.getFileText(
      '$pathPrefix/$otherDeviceId/$filename',
    );
    if (text == null) continue;
    try {
      mergedLog = mergeLogs(mergedLog, decode(text));
    } on FormatException {
      continue;
    } on TypeError {
      continue;
    }
    // Only remembered once the merge succeeded: a corrupt push must be
    // retried next tick, not marked as seen.
    seenRevs[otherDeviceId] = remoteRev ?? revisionOf(text);
  }

  final encoded = encode(mergedLog);
  final rev = revisionOf(encoded);
  final unchanged = stateStore != null && rev == state.pushedRev;
  if (!unchanged) {
    await client.putFileText(
      '$pathPrefix/$deviceId/$filename',
      encoded,
      message: commitMessage,
    );
    if (stateStore != null) {
      // Published after the log, never before: a peer that cached "seen rev
      // X" against a log it never received would skip it forever.
      await client.putFileText('$revs/$deviceId', rev, message: commitMessage);
    }
  }
  await stateStore?.save(SyncState(pushedRev: rev, peerRevs: seenRevs));
  return mergedLog;
}

/// Where revisions live for a given [pathPrefix]: a `revs` sibling of the
/// device directory, e.g. `diet-guard-sync/devices` -> `diet-guard-sync/revs`
/// and `todo-sync/notes` -> `todo-sync/revs`.
String defaultRevsPath(String pathPrefix) {
  final cut = pathPrefix.lastIndexOf('/');
  return cut < 0 ? '$pathPrefix/revs' : '${pathPrefix.substring(0, cut)}/revs';
}

/// Reads every peer's published revision, cheaply where the backend allows.
///
/// Degrades to an empty map -- meaning "fetch everything", the old behaviour
/// -- on any backend without [BulkMapReader], so correctness never depends on
/// the optimisation being available.
Future<Map<String, String>> _remoteRevs(
  RemoteStore client,
  String revsPath,
) async {
  // A pattern bind rather than `is!` + promotion: BulkMapReader is not a
  // subtype of RemoteStore, and Dart only promotes to subtypes of the
  // declared type -- so the intersection has to be named explicitly.
  if (client case final BulkMapReader reader) {
    return reader.getStringMap(revsPath);
  }
  return const {};
}
