/// Tests for the dual-write decorator used during the GitHub -> Firebase
/// cutover.
///
/// The asymmetry is the whole point and is what these assert: a primary
/// failure must fail the tick, a mirror failure must not, and reads must
/// consult both so that a half-migrated app (one device moved, one not) still
/// converges in both directions.
library;

import 'package:crdt_sync/crdt_sync.dart';
import 'package:test/test.dart';

/// A scriptable in-memory [RemoteStore] that can be told to fail.
class _FakeStore implements RemoteStore, BulkMapReader {
  _FakeStore({Map<String, String>? files, this.failing = false})
    : files = files ?? {};

  final Map<String, String> files;
  bool failing;
  final List<String> writes = [];
  bool closed = false;

  void _guard(String what) {
    if (failing) throw RemoteSyncError('$what failed');
  }

  @override
  Future<List<String>> listDirectory(String path) async {
    _guard('list');
    return files.keys
        .where((key) => key.startsWith('$path/'))
        .map((key) => key.substring(path.length + 1).split('/').first)
        .toSet()
        .toList();
  }

  @override
  Future<String?> getFileText(String path) async {
    _guard('read');
    return files[path];
  }

  @override
  Future<void> putFileText(
    String path,
    String text, {
    required String message,
  }) async {
    _guard('write');
    writes.add(path);
    files[path] = text;
  }

  @override
  Future<Map<String, String>> getStringMap(String path) async {
    _guard('map read');
    return {
      for (final entry in files.entries)
        if (entry.key.startsWith('$path/'))
          entry.key.substring(path.length + 1): entry.value,
    };
  }

  @override
  Future<void> deleteFile(String path, {String message = ''}) async {
    _guard('delete');
    files.remove(path);
  }

  @override
  Future<bool> canAccessRemote() async => !failing;

  @override
  void close() => closed = true;
}

/// A store with no bulk-map capability, standing in for [GitHubClient].
class _FakeStoreWithoutBulkRead implements RemoteStore {
  _FakeStoreWithoutBulkRead([Map<String, String>? files])
    : _inner = _FakeStore(files: files);

  final _FakeStore _inner;

  @override
  Future<List<String>> listDirectory(String path) => _inner.listDirectory(path);
  @override
  Future<String?> getFileText(String path) => _inner.getFileText(path);
  @override
  Future<void> putFileText(String p, String t, {required String message}) =>
      _inner.putFileText(p, t, message: message);
  @override
  Future<void> deleteFile(String path, {String message = ''}) =>
      _inner.deleteFile(path, message: message);
  @override
  Future<bool> canAccessRemote() => _inner.canAccessRemote();
  @override
  void close() => _inner.close();
}

({
  MirrorStore store,
  _FakeStore primary,
  _FakeStore mirror,
  List<String> failures,
})
_mirror({
  Map<String, String>? primaryFiles,
  Map<String, String>? mirrorFiles,
  bool primaryFailing = false,
  bool mirrorFailing = false,
}) {
  final primary = _FakeStore(files: primaryFiles, failing: primaryFailing);
  final mirror = _FakeStore(files: mirrorFiles, failing: mirrorFailing);
  final failures = <String>[];
  return (
    store: MirrorStore(
      primary: primary,
      mirror: mirror,
      onMirrorFailure: (operation, _) => failures.add(operation),
    ),
    primary: primary,
    mirror: mirror,
    failures: failures,
  );
}

void main() {
  group('primary read fallback', () {
    test('getFileText falls back to the mirror', () async {
      final m = _mirror(
        primaryFailing: true,
        mirrorFiles: {'ns/phone/log.json': '{}'},
      );
      expect(await m.store.getFileText('ns/phone/log.json'), '{}');
    });

    test('getFileText throws when both fail', () async {
      final m = _mirror(primaryFailing: true, mirrorFailing: true);
      await expectLater(
        () => m.store.getFileText('ns/phone/log.json'),
        throwsA(isA<RemoteSyncError>()),
      );
    });

    test('getFileText throws when primary fails and mirror lacks it', () async {
      // A reachable mirror that simply does not hold the file is not an
      // answer either, since the primary's copy was never read.
      final m = _mirror(primaryFailing: true);
      await expectLater(
        () => m.store.getFileText('ns/phone/log.json'),
        throwsA(isA<RemoteSyncError>()),
      );
    });

    test('getStringMap falls back to the mirror', () async {
      final m = _mirror(
        primaryFailing: true,
        mirrorFiles: {'ns/revs/phone': 'r1'},
      );
      expect(await m.store.getStringMap('ns/revs'), {'phone': 'r1'});
    });

    test('getStringMap throws when both fail', () async {
      final m = _mirror(primaryFailing: true, mirrorFailing: true);
      await expectLater(
        () => m.store.getStringMap('ns/revs'),
        throwsA(isA<RemoteSyncError>()),
      );
    });

    test('getStringMap tolerates a mirror that cannot bulk-read', () async {
      // A mirror with no bulk-read capability (GitHub) contributes nothing,
      // but that is not a failure -- it simply has no revisions to add, so a
      // working primary's map must still come back.
      final store = MirrorStore(
        primary: _FakeStore(files: {'ns/revs/pc': 'r1'}),
        mirror: _FakeStoreWithoutBulkRead(),
      );
      expect(await store.getStringMap('ns/revs'), {'pc': 'r1'});
    });

    test('writes stay fail-closed on a primary failure', () async {
      // The read fix must NOT loosen writes: an unaccepted write has not
      // happened, so it must still fail the tick.
      final m = _mirror(primaryFailing: true);
      await expectLater(
        () => m.store.putFileText('ns/pc/log.json', '{}', message: 'm'),
        throwsA(isA<RemoteSyncError>()),
      );
      await expectLater(
        () => m.store.deleteFile('ns/pc/log.json'),
        throwsA(isA<RemoteSyncError>()),
      );
    });
  });
}
