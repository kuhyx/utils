import 'dart:async';
import 'dart:convert';

import 'hlc.dart';
import 'log.dart';
import 'record.dart';

/// Serializes a [Log] to canonical JSON text: a top-level object mapping each
/// record id to its [Record.toJson]. Mirrors `crdt_sync._store.dump_log` on
/// the Python side, so a log written by one language parses in the other.
String logToJson(Log log) => jsonEncode({
  for (final entry in log.entries) entry.key: entry.value.toJson(),
});

/// Parses text produced by [logToJson] back into a [Log].
///
/// Throws [FormatException] (bad JSON) or [TypeError] (valid JSON, wrong
/// shape) on a corrupt payload -- callers persisting to disk should treat
/// both as "start empty", see [LogPersistence]-backed [LogStore.load].
Log logFromJson(String text) {
  final raw = jsonDecode(text) as Map<String, dynamic>;
  return raw.map(
    (id, value) =>
        MapEntry(id, Record.fromJson((value as Map).cast<String, dynamic>())),
  );
}

/// A durable, string-in/string-out persistence port for a [LogStore].
///
/// Kept deliberately free of `dart:io` so [LogStore] stays pure Dart (usable
/// on web and trivially faked in tests). A filesystem-backed implementation
/// lives behind the separate `package:crdt_sync/crdt_sync_io.dart` entrypoint;
/// tests inject an in-memory one.
abstract class LogPersistence {
  /// Returns the stored text, or `null` if nothing has been persisted yet.
  Future<String?> read();

  /// Overwrites the stored text with [text].
  Future<void> write(String text);
}

/// An in-memory [Log] with reactive change notifications, backed by a
/// [LogPersistence] port.
///
/// This is the local-persistence half that the merge scheme itself
/// (`Hlc`/`Record`/`Log`) deliberately omits. It is domain-agnostic:
/// filtering, sorting and searching over [values] is the caller's job -- the
/// store knows nothing about what fields a record carries. A consumer's typical
/// reactive read is `store.changes.map((_) => store.values.where(pred))`.
///
/// The store owns this node's logical clock: every mutation it performs
/// (a [delete] tombstone) is stamped with a monotonic [Hlc] for [nodeId], and
/// callers building their own records should take field clocks from [nextHlc]
/// so the whole device shares one monotonic sequence.
class LogStore {
  /// Creates a store for [nodeId] persisting through [persistence].
  ///
  /// Call [load] once before reading [values] to hydrate from storage.
  // Dart forbids private named params, so these can't be initializing
  // formals; assign them explicitly.
  // ignore_for_file: prefer_initializing_formals
  LogStore({required LogPersistence persistence, required String nodeId})
    : _persistence = persistence,
      _nodeId = nodeId;

  final LogPersistence _persistence;
  final String _nodeId;
  final Log _log = {};
  final StreamController<void> _changes = StreamController<void>.broadcast();
  Hlc? _lastHlc;

  /// Fires (with no payload) after every mutation that reaches storage.
  ///
  /// A UI listens here and re-derives its view from [values]; the event
  /// carries nothing because the store is not the place that knows how to
  /// shape a domain view.
  Stream<void> get changes => _changes.stream;

  /// The current records, tombstones included. Callers filter as needed.
  Iterable<Record> get values => _log.values;

  /// Returns the record for [id], or `null` if absent.
  Record? get(String id) => _log[id];

  /// An unmodifiable snapshot of the whole log, e.g. to hand to `syncLog`.
  Log snapshot() => Map.unmodifiable(_log);

  /// Returns the next monotonic [Hlc] for this node, advancing the clock.
  ///
  /// Callers stamp their own record fields with this so a device's writes and
  /// the store's own delete tombstones share one strictly increasing sequence.
  Hlc nextHlc() {
    final next = Hlc.newTick(_nodeId, previous: _lastHlc);
    _lastHlc = next;
    return next;
  }

  /// Hydrates the in-memory log from storage, returning a snapshot.
  ///
  /// A missing or corrupt payload is treated as an empty log (never an error),
  /// so a truncated write can't brick the app -- it just loses the unwritten
  /// tail, exactly as the file-storage mirror in diet_guard does.
  Future<Log> load() async {
    final text = await _persistence.read();
    _log.clear();
    if (text != null) {
      try {
        _log.addAll(logFromJson(text));
      } on FormatException {
        _log.clear();
      } on TypeError {
        _log.clear();
      }
    }
    _trackLatestHlc();
    return snapshot();
  }

  /// Inserts or replaces [record] and persists.
  ///
  /// The caller owns the record's field clocks (take them from [nextHlc]);
  /// the store does not re-stamp them, so an unchanged re-upsert is a no-op
  /// under a later merge.
  Future<void> upsert(Record record) async {
    _log[record.id] = record;
    _trackHlcsOf(record);
    await _persist();
  }

  /// Tombstones the record with [id] in place (sticky CRDT delete) and
  /// persists. No-op if [id] is absent or already deleted.
  ///
  /// Tombstoning rather than removing is what stops a delete from being
  /// silently undone when an older, still-present copy is pulled from another
  /// device on the next sync.
  Future<void> delete(String id) async {
    final existing = _log[id];
    if (existing == null || existing.deleted) return;
    _log[id] = Record(
      id: existing.id,
      fields: existing.fields,
      deleted: true,
      deletedHlc: nextHlc(),
    );
    await _persist();
  }

  /// Replaces the entire log (e.g. with a post-merge result from `syncLog`)
  /// and persists.
  Future<void> replaceAll(Log merged) async {
    _log
      ..clear()
      ..addAll(merged);
    _trackLatestHlc();
    await _persist();
  }

  /// Releases the [changes] stream. The store is unusable afterwards.
  Future<void> close() => _changes.close();

  Future<void> _persist() async {
    await _persistence.write(logToJson(_log));
    if (!_changes.isClosed) _changes.add(null);
  }

  void _trackLatestHlc() {
    for (final record in _log.values) {
      _trackHlcsOf(record);
    }
  }

  void _trackHlcsOf(Record record) {
    for (final field in record.fields.values) {
      _bumpLastHlc(field.$2);
    }
    final deletedHlc = record.deletedHlc;
    if (deletedHlc != null) _bumpLastHlc(deletedHlc);
  }

  void _bumpLastHlc(Hlc candidate) {
    if (_lastHlc == null || candidate > _lastHlc!) _lastHlc = candidate;
  }
}
