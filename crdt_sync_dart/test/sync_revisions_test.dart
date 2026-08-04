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

  group('revision publishing order', () {
    test('publishes the log before its revision', () async {
      // Reversed, a peer would cache "seen rev X" against a log it never
      // received, and skip it forever.
      final remote = _FakeRemote({});
      await _tick(remote, InMemorySyncStateStore(), local: _log('a', '1'));
      expect(
        remote.writes.indexOf('ns/devices/pc/log.json'),
        lessThan(remote.writes.indexOf('ns/revs/pc')),
      );
    });

    test('each device writes only its own revision key', () async {
      // Per-device keys rather than one shared map: a whole-map write would
      // erase every other device's entry, after which those peers would look
      // permanently unchanged and never be fetched again.
      final remote = _FakeRemote({'ns/revs/phone': 'peer-rev'});
      await _tick(remote, InMemorySyncStateStore(), local: _log('a', '1'));
      expect(remote.files['ns/revs/phone'], 'peer-rev');
    });
  });

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
