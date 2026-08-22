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
}
