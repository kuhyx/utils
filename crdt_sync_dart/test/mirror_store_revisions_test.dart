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
  group('revision maps', () {
    test('merge both backends, primary winning on conflict', () async {
      final m = _mirror(
        primaryFiles: {'ns/revs/pc': 'primary-rev'},
        mirrorFiles: {'ns/revs/pc': 'mirror-rev', 'ns/revs/phone': 'old-rev'},
      );
      expect(await m.store.getStringMap('ns/revs'), {
        'pc': 'primary-rev',
        // An un-migrated device publishes revisions only to the mirror;
        // without this it would look revision-less and be re-downloaded
        // every tick for the whole trial.
        'phone': 'old-rev',
      });
    });

    test('a mirror failure degrades to primary revisions only', () async {
      final m = _mirror(
        primaryFiles: {'ns/revs/pc': 'primary-rev'},
        mirrorFailing: true,
      );
      expect(await m.store.getStringMap('ns/revs'), {'pc': 'primary-rev'});
      expect(m.failures, ['getStringMap ns/revs']);
    });

    test('a backend without bulk reads simply contributes nothing', () async {
      final store = MirrorStore(
        primary: _FakeStore(files: {'ns/revs/pc': 'primary-rev'}),
        mirror: _FakeStoreWithoutBulkRead({'ns/revs/phone': 'ignored'}),
      );
      expect(await store.getStringMap('ns/revs'), {'pc': 'primary-rev'});
    });

    test('is empty when the primary has no bulk reads either', () async {
      final store = MirrorStore(
        primary: _FakeStoreWithoutBulkRead(),
        mirror: _FakeStoreWithoutBulkRead(),
      );
      expect(await store.getStringMap('ns/revs'), isEmpty);
    });
  });

  group('lifecycle', () {
    test('canAccessRemote reports only the primary', () async {
      // A Test-connection button must not report success because the backend
      // being retired happens to answer.
      final m = _mirror(primaryFailing: true);
      expect(await m.store.canAccessRemote(), isFalse);
      final healthy = _mirror(mirrorFailing: true);
      expect(await healthy.store.canAccessRemote(), isTrue);
    });

    test('close releases both backends', () {
      final m = _mirror();
      m.store.close();
      expect(m.primary.closed, isTrue);
      expect(m.mirror.closed, isTrue);
    });

    test('a mirror failure with no handler is still swallowed', () async {
      final store = MirrorStore(
        primary: _FakeStore(),
        mirror: _FakeStore(failing: true),
      );
      await expectLater(
        store.putFileText('ns/pc/log.json', '{}', message: 'm'),
        completes,
      );
    });

    test('is itself a RemoteStore, so syncLog accepts it', () {
      expect(_mirror().store, isA<RemoteStore>());
    });
  });

  group('end to end through syncLog', () {
    test('a half-migrated pair still converges both ways', () async {
      // desktop is on Firebase+mirror; phone has not migrated and still
      // writes only to GitHub. Both must end up with both records.
      final github = _FakeStore();
      final firebase = _FakeStore();

      Log log(String id, String nodeId) => {
        id: Record(
          id: id,
          fields: {
            'v': (id, Hlc(wallTimeMs: 1000, counter: 0, nodeId: nodeId)),
          },
        ),
      };
      // The library's own serialization, so this exercises the same
      // encoding the apps use rather than a test-only one.
      const encode = logToJson;
      const decode = logFromJson;

      // Un-migrated phone: GitHub only.
      await syncLog(
        client: github,
        deviceId: 'phone',
        pathPrefix: 'ns/devices',
        localLog: log('from-phone', 'node-phone'),
        encode: encode,
        decode: decode,
      );

      // Migrated desktop: Firebase primary, GitHub mirror.
      final merged = await syncLog(
        client: MirrorStore(primary: firebase, mirror: github),
        deviceId: 'desktop',
        pathPrefix: 'ns/devices',
        localLog: log('from-desktop', 'node-desktop'),
        encode: encode,
        decode: decode,
      );

      expect(merged.keys, containsAll(['from-phone', 'from-desktop']));
      // The desktop's merged result is mirrored back to GitHub, so the
      // un-migrated phone sees it on its next tick.
      expect(github.files['ns/devices/desktop/log.json'], isNotNull);
    });
  });
}
