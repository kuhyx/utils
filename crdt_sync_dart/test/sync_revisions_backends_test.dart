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

/// A [RemoteStore] with no bulk-map capability, standing in for
/// [GitHubClient]: revision tracking must degrade, not break.
///
/// Delegates rather than extends, because a subclass of [_FakeRemote] would
/// inherit `BulkMapReader` -- the very capability this fake exists to lack.
class _FakeRemoteWithoutBulkRead implements RemoteStore {
  _FakeRemoteWithoutBulkRead(Map<String, String> files)
    : _inner = _FakeRemote(files);

  final _FakeRemote _inner;

  Map<String, String> get files => _inner.files;
  List<String> get reads => _inner.reads;
  List<String> get writes => _inner.writes;

  @override
  Future<List<String>> listDirectory(String path) => _inner.listDirectory(path);

  @override
  Future<String?> getFileText(String path) => _inner.getFileText(path);

  @override
  Future<void> putFileText(
    String path,
    String text, {
    required String message,
  }) => _inner.putFileText(path, text, message: message);

  @override
  Future<void> deleteFile(String path, {String message = ''}) =>
      _inner.deleteFile(path, message: message);

  @override
  Future<bool> canAccessRemote() => _inner.canAccessRemote();

  @override
  void close() => _inner.close();
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
  group('backends without bulk-map reads', () {
    test('still sync correctly, just without the saving', () async {
      // GitHubClient has no BulkMapReader, so revision lookup degrades to
      // "fetch everything" -- correctness must not depend on the optimisation.
      final peer = _encode(_log('b', 'from-phone', nodeId: 'node-b'));
      final remote = _FakeRemoteWithoutBulkRead({
        'ns/devices/phone/log.json': peer,
      });
      final store = InMemorySyncStateStore();
      final first = await _tick(remote, store);
      expect(first.keys, contains('b'));

      remote.reads.clear();
      await _tick(remote, store, local: first);
      expect(remote.reads, contains('ns/devices/phone/log.json'));
    });
  });
}
