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
  group('writes', () {
    test('go to both backends', () async {
      final m = _mirror();
      await m.store.putFileText('ns/pc/log.json', '{}', message: 'm');
      expect(m.primary.writes, ['ns/pc/log.json']);
      expect(m.mirror.writes, ['ns/pc/log.json']);
    });

    test('a primary failure fails the tick', () async {
      // Fail-closed: the primary is authoritative, so a sync that could not
      // write it must not be reported as successful.
      final m = _mirror(primaryFailing: true);
      await expectLater(
        () => m.store.putFileText('ns/pc/log.json', '{}', message: 'm'),
        throwsA(isA<RemoteSyncError>()),
      );
    });

    test('a mirror failure is loud but does not fail the tick', () async {
      final m = _mirror(mirrorFailing: true);
      await m.store.putFileText('ns/pc/log.json', '{}', message: 'm');
      expect(m.primary.writes, ['ns/pc/log.json']);
      expect(m.failures, ['putFileText ns/pc/log.json']);
    });

    test('deletes behave the same way', () async {
      final m = _mirror(
        primaryFiles: {'ns/pc/log.json': '{}'},
        mirrorFiles: {'ns/pc/log.json': '{}'},
        mirrorFailing: true,
      );
      await m.store.deleteFile('ns/pc/log.json');
      expect(m.primary.files, isEmpty);
      expect(m.failures, ['deleteFile ns/pc/log.json']);
    });

    test('a primary delete failure fails the tick', () async {
      final m = _mirror(primaryFailing: true);
      await expectLater(
        () => m.store.deleteFile('ns/pc/log.json'),
        throwsA(isA<RemoteSyncError>()),
      );
    });
  });

  group('reads consult both backends', () {
    test('prefer the primary when it has the file', () async {
      final m = _mirror(
        primaryFiles: {'ns/pc/log.json': 'from-primary'},
        mirrorFiles: {'ns/pc/log.json': 'from-mirror'},
      );
      expect(await m.store.getFileText('ns/pc/log.json'), 'from-primary');
    });

    test('fall back to the mirror for an un-migrated device', () async {
      // This is why reads are not primary-only: a migrated desktop must
      // still see an un-migrated phone's writes, or convergence silently
      // becomes one-directional with no error raised.
      final m = _mirror(mirrorFiles: {'ns/phone/log.json': 'from-mirror'});
      expect(await m.store.getFileText('ns/phone/log.json'), 'from-mirror');
    });

    test('return null when neither backend has the file', () async {
      final m = _mirror();
      expect(await m.store.getFileText('ns/nobody/log.json'), isNull);
    });

    test('a mirror read failure degrades to the primary answer', () async {
      final m = _mirror(mirrorFailing: true);
      expect(await m.store.getFileText('ns/pc/log.json'), isNull);
      expect(m.failures, ['getFileText ns/pc/log.json']);
    });

    test('a primary read failure with nothing in the mirror throws', () async {
      // Named for what it actually exercises: the primary throws AND the
      // mirror does not hold the file, so neither side has an answer. A
      // primary failure alone no longer fails the read -- see the
      // "primary read fallback" group.
      final m = _mirror(primaryFailing: true);
      await expectLater(
        () => m.store.getFileText('ns/pc/log.json'),
        throwsA(isA<RemoteSyncError>()),
      );
    });
  });

  group('listDirectory', () {
    test('unions devices from both backends', () async {
      final m = _mirror(
        primaryFiles: {'ns/pc/log.json': '{}'},
        mirrorFiles: {'ns/phone/log.json': '{}'},
      );
      expect(await m.store.listDirectory('ns'), containsAll(['pc', 'phone']));
    });

    test('does not duplicate a device present in both', () async {
      final m = _mirror(
        primaryFiles: {'ns/pc/log.json': '{}'},
        mirrorFiles: {'ns/pc/log.json': '{}'},
      );
      expect(await m.store.listDirectory('ns'), ['pc']);
    });

    test('a mirror failure degrades to the primary list', () async {
      final m = _mirror(
        primaryFiles: {'ns/pc/log.json': '{}'},
        mirrorFailing: true,
      );
      expect(await m.store.listDirectory('ns'), ['pc']);
      expect(m.failures, ['listDirectory ns']);
    });

    test('a primary failure degrades to the mirror list', () async {
      // READS are resilient on both sides: a Firebase outage must not hide
      // the mirror's devices. This used to throw, which made a primary outage
      // look like "no devices exist" -- the union read silently degrading to
      // nothing, precisely when the fallback was needed.
      final m = _mirror(
        primaryFailing: true,
        mirrorFiles: {'ns/phone/log.json': '{}'},
      );
      expect(await m.store.listDirectory('ns'), ['phone']);
    });

    test('both backends failing throws', () async {
      // With no answer from either side, fail closed: an empty list is
      // indistinguishable from "no devices", and callers act on that.
      final m = _mirror(primaryFailing: true, mirrorFailing: true);
      await expectLater(
        () => m.store.listDirectory('ns'),
        throwsA(isA<RemoteSyncError>()),
      );
    });
  });

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
