// Offline-first contract: writes are stored locally first and readable at
// once; an unreachable remote makes syncLog throw without losing the write;
// pulled peer data is cached locally for offline reads.

import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:test/test.dart';

class _MemPersistence implements LogPersistence {
  String? text;

  @override
  Future<String?> read() async => text;

  @override
  Future<void> write(String t) async => text = t;
}

/// A remote that is unreachable: every call throws RemoteSyncError.
class _OfflineRemote implements RemoteStore {
  @override
  Future<List<String>> listDirectory(String path) async =>
      throw RemoteSyncError('offline');

  @override
  Future<String?> getFileText(String path) async =>
      throw RemoteSyncError('offline');

  @override
  Future<void> putFileText(
    String path,
    String text, {
    required String message,
  }) async => throw RemoteSyncError('offline');

  @override
  Future<void> deleteFile(String path, {String? message}) async =>
      throw RemoteSyncError('offline');

  @override
  Future<bool> canAccessRemote() async => throw RemoteSyncError('offline');

  @override
  void close() {}
}

/// An in-memory reachable remote: a `Map<String, String>` of files;
/// listDirectory returns the distinct next path segment of every key under
/// [pathPrefix].
class _MemRemote implements RemoteStore {
  final Map<String, String> files = {};

  @override
  Future<List<String>> listDirectory(String path) async {
    final prefix = '$path/';
    return files.keys
        .where((key) => key.startsWith(prefix))
        .map((key) => key.substring(prefix.length).split('/').first)
        .toSet()
        .toList();
  }

  @override
  Future<String?> getFileText(String path) async => files[path];

  @override
  Future<void> putFileText(
    String path,
    String text, {
    required String message,
  }) async => files[path] = text;

  @override
  Future<void> deleteFile(String path, {String? message}) async {
    files.remove(path);
  }

  @override
  Future<bool> canAccessRemote() async => true;

  @override
  void close() {}
}

String _encode(Log log) =>
    jsonEncode(log.map((id, r) => MapEntry(id, r.toJson())));

Log _decode(String text) => (jsonDecode(text) as Map<String, dynamic>).map(
  (id, d) => MapEntry(id, Record.fromJson(d as Map<String, dynamic>)),
);

void main() {
  group('offline-first contract', () {
    test(
      'a write is readable at once and survives a restart with no network',
      () async {
        final persistence = _MemPersistence();
        final store = LogStore(persistence: persistence, nodeId: 'phone');
        await store.load();
        await store.upsert(
          Record(id: 'a', fields: {'title': ('milk', store.nextHlc())}),
        );

        // Readable at once, no remote involved; a fresh store on the same
        // persistence sees it after load.
        expect(store.get('a'), isNotNull);
        final restarted = LogStore(persistence: persistence, nodeId: 'phone');
        await restarted.load();
        expect(restarted.get('a'), isNotNull);
      },
    );

    test('a failed tick leaves the local log intact', () async {
      final persistence = _MemPersistence();
      final store = LogStore(persistence: persistence, nodeId: 'phone');
      await store.load();
      await store.upsert(
        Record(id: 'a', fields: {'title': ('milk', store.nextHlc())}),
      );

      await expectLater(
        syncLog(
          client: _OfflineRemote(),
          deviceId: 'phone',
          pathPrefix: 'app-sync/devices',
          localLog: store.snapshot(),
          encode: _encode,
          decode: _decode,
        ),
        throwsA(isA<RemoteSyncError>()),
      );

      expect(store.get('a'), isNotNull);
      expect(persistence.text, contains('"a"'));
    });

    test('the offline write is pushed once the remote is back', () async {
      final persistence = _MemPersistence();
      final store = LogStore(persistence: persistence, nodeId: 'phone');
      await store.load();
      await store.upsert(
        Record(id: 'a', fields: {'title': ('milk', store.nextHlc())}),
      );
      // Offline tick fails; once the remote is back it pushes the write.
      await expectLater(
        syncLog(
          client: _OfflineRemote(),
          deviceId: 'phone',
          pathPrefix: 'app-sync/devices',
          localLog: store.snapshot(),
          encode: _encode,
          decode: _decode,
        ),
        throwsA(isA<RemoteSyncError>()),
      );
      final remote = _MemRemote();
      await syncLog(
        client: remote,
        deviceId: 'phone',
        pathPrefix: 'app-sync/devices',
        localLog: store.snapshot(),
        encode: _encode,
        decode: _decode,
      );

      final pushed = remote.files['app-sync/devices/phone/log.json'];
      expect(pushed, isNotNull);
      expect(_decode(pushed!).containsKey('a'), isTrue);
    });

    test('pulled records are stored locally, readable offline', () async {
      final persistence = _MemPersistence();
      final store = LogStore(persistence: persistence, nodeId: 'phone');
      await store.load();

      final peerStore = LogStore(persistence: _MemPersistence(), nodeId: 'pc');
      await peerStore.load();
      await peerStore.upsert(
        Record(id: 'b', fields: {'title': ('bread', peerStore.nextHlc())}),
      );

      final remote = _MemRemote()
        ..files['app-sync/devices/pc/log.json'] = _encode(peerStore.snapshot());
      final merged = await syncLog(
        client: remote,
        deviceId: 'phone',
        pathPrefix: 'app-sync/devices',
        localLog: store.snapshot(),
        encode: _encode,
        decode: _decode,
      );
      await store.replaceAll(merged);
      final restarted = LogStore(persistence: persistence, nodeId: 'phone');
      await restarted.load();
      expect(restarted.get('b'), isNotNull);
    });
  });
}
