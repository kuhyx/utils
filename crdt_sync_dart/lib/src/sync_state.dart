import 'dart:convert';

import 'store.dart';

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
