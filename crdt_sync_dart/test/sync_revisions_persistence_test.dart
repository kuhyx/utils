/// Tests for the revision tracking that keeps sync inside the free tier.
///
/// Two savings, both measured against the GitHub-backed history this
/// replaces: 88.3% of pushes there were byte-identical no-ops, and every tick
/// re-downloaded every peer's whole log regardless of whether it had changed.
/// These tests assert the *request counts*, since that -- not the merge
/// result -- is what the free-tier headroom depends on.
library;

import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:test/test.dart';

Log _log(String id, String value, {String nodeId = 'node-a'}) => {
  id: Record(
    id: id,
    fields: {
      'value': (value, Hlc(wallTimeMs: 1000, counter: 0, nodeId: nodeId)),
    },
  ),
};

String _encode(Log log) =>
    jsonEncode(log.map((id, record) => MapEntry(id, record.toJson())));

Log _decode(String text) => (jsonDecode(text) as Map<String, dynamic>).map(
  (id, data) => MapEntry(id, Record.fromJson(data as Map<String, dynamic>)),
);

/// An in-memory [RemoteStore] that also serves revision maps in one read,
/// standing in for [FirebaseRestClient]. Counts every call so tests can
/// assert on traffic rather than on results.
class _FakeRemote implements RemoteStore, BulkMapReader {
  _FakeRemote(this.files);

  final Map<String, String> files;
  final List<String> reads = [];
  final List<String> writes = [];
  final List<String> mapReads = [];

  @override
  Future<List<String>> listDirectory(String path) async => files.keys
      .where((key) => key.startsWith('$path/'))
      .map((key) => key.substring(path.length + 1).split('/').first)
      .toSet()
      .toList();

  @override
  Future<String?> getFileText(String path) async {
    reads.add(path);
    return files[path];
  }

  @override
  Future<void> putFileText(
    String path,
    String text, {
    required String message,
  }) async {
    writes.add(path);
    files[path] = text;
  }

  @override
  Future<Map<String, String>> getStringMap(String path) async {
    mapReads.add(path);
    return {
      for (final entry in files.entries)
        if (entry.key.startsWith('$path/'))
          entry.key.substring(path.length + 1): entry.value,
    };
  }

  @override
  Future<void> deleteFile(String path, {String message = ''}) async =>
      files.remove(path);

  @override
  Future<bool> canAccessRemote() async => true;

  @override
  void close() {}
}

Future<Log> _tick(
  RemoteStore remote,
  SyncStateStore? store, {
  Log local = const {},
  String deviceId = 'pc',
}) => syncLog(
  client: remote,
  deviceId: deviceId,
  pathPrefix: 'ns/devices',
  localLog: local,
  encode: _encode,
  decode: _decode,
  stateStore: store,
);

void main() {
  group('PersistedSyncStateStore', () {
    test('round-trips state through persistence', () async {
      final persistence = _FakePersistence();
      const state = SyncState(
        pushedRev: 'rev-local',
        peerRevs: {'phone': 'rev-phone'},
      );

      await PersistedSyncStateStore(persistence).save(state);
      final loaded = await PersistedSyncStateStore(persistence).load();

      // A *separate* store instance reads it back: that is the whole point --
      // surviving the cold start that an in-memory store does not.
      expect(loaded.pushedRev, 'rev-local');
      expect(loaded.peerRevs, {'phone': 'rev-phone'});
    });

    test('survives a cold start, so peers are not re-downloaded', () async {
      // The free-tier claim on mobile rests on this: a fresh process must
      // still skip an unchanged peer.
      final persistence = _FakePersistence();
      final remote = _FakeRemote({
        'ns/devices/phone/log.json': _encode(_log('a', '1')),
        'ns/revs/phone': revisionOf(_encode(_log('a', '1'))),
      });

      await _tick(remote, PersistedSyncStateStore(persistence));
      remote.reads.clear();
      await _tick(remote, PersistedSyncStateStore(persistence));

      expect(remote.reads, isNot(contains('ns/devices/phone/log.json')));
    });

    test('reports nothing remembered when absent', () async {
      final loaded = await PersistedSyncStateStore(_FakePersistence()).load();

      expect(loaded.pushedRev, isNull);
      expect(loaded.peerRevs, isEmpty);
    });

    test('degrades to remembering nothing when empty', () async {
      final loaded = await PersistedSyncStateStore(
        _FakePersistence(text: ''),
      ).load();

      expect(loaded.pushedRev, isNull);
    });

    test('degrades to remembering nothing when corrupt', () async {
      // Costs one tick of extra traffic rather than failing the sync.
      final loaded = await PersistedSyncStateStore(
        _FakePersistence(text: 'not json{'),
      ).load();

      expect(loaded.pushedRev, isNull);
    });

    test('degrades to remembering nothing when not an object', () async {
      final loaded = await PersistedSyncStateStore(
        _FakePersistence(text: '["a list"]'),
      ).load();

      expect(loaded.pushedRev, isNull);
    });

    test('degrades to remembering nothing when the read throws', () async {
      // An unreadable file must not fail the tick.
      final loaded = await PersistedSyncStateStore(
        _FakePersistence(readThrows: true),
      ).load();

      expect(loaded.pushedRev, isNull);
    });
  });
}

/// A [LogPersistence] fake with injectable failure modes.
class _FakePersistence implements LogPersistence {
  _FakePersistence({this.text, this.readThrows = false});

  String? text;
  final bool readThrows;

  @override
  Future<String?> read() async {
    if (readThrows) throw const FormatException('unreadable');
    return text;
  }

  @override
  Future<void> write(String value) async => text = value;
}
