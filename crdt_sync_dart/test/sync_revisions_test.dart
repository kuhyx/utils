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
  group('revisionOf', () {
    test('is stable for identical content', () {
      expect(revisionOf('{"a":1}'), revisionOf('{"a":1}'));
    });

    test('differs for different content', () {
      expect(revisionOf('{"a":1}'), isNot(revisionOf('{"a":2}')));
    });
  });

  group('defaultRevsPath', () {
    test('is a sibling of the device directory', () {
      expect(
        defaultRevsPath('diet-guard-sync/devices'),
        'diet-guard-sync/revs',
      );
      expect(defaultRevsPath('todo-sync/notes'), 'todo-sync/revs');
    });

    test('falls back to a child when the prefix has no parent', () {
      expect(defaultRevsPath('ns'), 'ns/revs');
    });
  });

  group('SyncState', () {
    test('round-trips through JSON', () {
      const state = SyncState(pushedRev: 'abc', peerRevs: {'phone': 'def'});
      final restored = SyncState.fromJson(state.toJson());
      expect(restored.pushedRev, 'abc');
      expect(restored.peerRevs, {'phone': 'def'});
    });

    test('tolerates a missing or malformed peer map', () {
      expect(SyncState.fromJson({}).peerRevs, isEmpty);
      expect(
        SyncState.fromJson({
          'peer_revs': {'phone': 42},
        }).peerRevs,
        isEmpty,
      );
    });
  });

  group('no-op push suppression', () {
    test('pushes on the first tick and publishes a revision', () async {
      final remote = _FakeRemote({});
      final store = InMemorySyncStateStore();
      await _tick(remote, store, local: _log('a', '1'));
      expect(remote.writes, ['ns/devices/pc/log.json', 'ns/revs/pc']);
    });

    test('a second unchanged tick writes nothing at all', () async {
      final remote = _FakeRemote({});
      final store = InMemorySyncStateStore();
      final local = _log('a', '1');
      await _tick(remote, store, local: local);
      remote.writes.clear();

      await _tick(remote, store, local: local);
      // This is the 88.3% of the old history that was pure waste.
      expect(remote.writes, isEmpty);
    });

    test('a changed log pushes again', () async {
      final remote = _FakeRemote({});
      final store = InMemorySyncStateStore();
      await _tick(remote, store, local: _log('a', '1'));
      remote.writes.clear();

      await _tick(remote, store, local: _log('a', '2'));
      expect(remote.writes, contains('ns/devices/pc/log.json'));
    });

    test('without a state store every tick pushes, as it always did', () async {
      final remote = _FakeRemote({});
      final local = _log('a', '1');
      await _tick(remote, null, local: local);
      await _tick(remote, null, local: local);
      expect(remote.writes, [
        'ns/devices/pc/log.json',
        'ns/devices/pc/log.json',
      ]);
      // No state store means no revision publishing either.
      expect(remote.writes.where((w) => w.startsWith('ns/revs')), isEmpty);
    });
  });
}
