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
  group('peer download suppression', () {
    test('downloads a peer whose revision it has never seen', () async {
      final peer = _encode(_log('b', 'from-phone', nodeId: 'node-b'));
      final remote = _FakeRemote({
        'ns/devices/phone/log.json': peer,
        'ns/revs/phone': revisionOf(peer),
      });
      final merged = await _tick(remote, InMemorySyncStateStore());
      expect(remote.reads, contains('ns/devices/phone/log.json'));
      expect(merged.keys, contains('b'));
    });

    test('skips the download when the peer revision is unchanged', () async {
      final peer = _encode(_log('b', 'from-phone', nodeId: 'node-b'));
      final remote = _FakeRemote({
        'ns/devices/phone/log.json': peer,
        'ns/revs/phone': revisionOf(peer),
      });
      final store = InMemorySyncStateStore();
      final first = await _tick(remote, store);
      remote.reads.clear();

      // The peer's records are already in the local log from tick one, so
      // re-downloading them is pure waste -- this is the ~700 MB/month that
      // the revision check removes.
      await _tick(remote, store, local: first);
      expect(remote.reads, isEmpty);
    });

    test('downloads again once the peer publishes a new revision', () async {
      final peerV1 = _encode(_log('b', 'v1', nodeId: 'node-b'));
      final remote = _FakeRemote({
        'ns/devices/phone/log.json': peerV1,
        'ns/revs/phone': revisionOf(peerV1),
      });
      final store = InMemorySyncStateStore();
      final first = await _tick(remote, store);
      remote.reads.clear();

      final peerV2 = _encode({
        ..._decode(peerV1),
        ..._log('c', 'v2', nodeId: 'node-b'),
      });
      remote.files['ns/devices/phone/log.json'] = peerV2;
      remote.files['ns/revs/phone'] = revisionOf(peerV2);

      final second = await _tick(remote, store, local: first);
      expect(remote.reads, contains('ns/devices/phone/log.json'));
      expect(second.keys, containsAll(['b', 'c']));
    });

    test('re-downloads a peer whose push was corrupt', () async {
      // A failed decode must not be remembered as seen, or the corruption
      // would be permanent.
      final remote = _FakeRemote({
        'ns/devices/phone/log.json': 'not json at all',
        'ns/revs/phone': revisionOf('not json at all'),
      });
      final store = InMemorySyncStateStore();
      await _tick(remote, store);
      remote.reads.clear();

      await _tick(remote, store);
      expect(remote.reads, contains('ns/devices/phone/log.json'));
    });

    test('downloads when the peer has published no revision yet', () async {
      // A device still running the pre-migration code publishes a log but no
      // revision; it must not be silently ignored.
      final peer = _encode(_log('b', 'from-phone', nodeId: 'node-b'));
      final remote = _FakeRemote({'ns/devices/phone/log.json': peer});
      final store = InMemorySyncStateStore();
      final merged = await _tick(remote, store);
      expect(merged.keys, contains('b'));
    });

    test('skips a peer that has nothing pushed yet', () async {
      final remote = _FakeRemote({'ns/devices/phone/other.txt': 'x'});
      final merged = await _tick(remote, InMemorySyncStateStore());
      expect(merged, isEmpty);
    });

    test('never reads its own device back', () async {
      final remote = _FakeRemote({
        'ns/devices/pc/log.json': _encode(_log('a', '1')),
        'ns/revs/pc': 'whatever',
      });
      await _tick(remote, InMemorySyncStateStore());
      expect(remote.reads, isEmpty);
    });
  });
}
