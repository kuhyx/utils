/// One-time copy from the plaintext prefix to `<prefix>-e2e`.
library;

import 'package:crdt_sync/crdt_sync.dart';
import 'package:test/test.dart';

import 'e2e_fakes.dart';

const _old = 'app/notes';

Future<E2eKey> _key(MemoryRemote remote, E2eLayout layout) => unlockE2e(
  store: remote,
  pathPrefix: layout.prefix,
  passphrase: 'pw',
  params: cheapArgon,
  e2ePath: layout.e2ePath,
);

MemoryRemote _plainRemote() => MemoryRemote({
  '$_old/phone/log.json': encodeLog(logOf({'a': 'milk', 'b': 'eggs'})),
  '$_old/pc/log.json': encodeLog(logOf({'c': 'tea'}, nodeId: 'node-b')),
});

void main() {
  final layout = E2eLayout.of(_old);

  test('layout puts ciphertext on a new prefix, revs apart from old', () {
    expect(layout.prefix, 'app/notes-e2e');
    expect(layout.revsPath, isNot(defaultRevsPath(_old)));
    expect(layout.e2ePath, startsWith('app/'));
  });

  test('copy seals every device log under the new prefix', () async {
    final remote = _plainRemote();
    final key = await _key(remote, layout);
    final report = await copyToEncrypted(
      store: remote,
      key: key,
      fromPrefix: _old,
      layout: layout,
    );
    expect(report.copied, 2);
    final blob = remote.files['app/notes-e2e/phone/log.json']!;
    expect(blob, isNot(contains('milk')));
    expect(blob, isNot(contains('"title"')));
    expect(remote.files['$_old/phone/log.json'], contains('milk'));
    final enc = EncryptingStore(
      remote,
      key,
      pathPrefix: layout.prefix,
      revsPath: layout.revsPath,
      e2ePath: layout.e2ePath,
    );
    final merged = await syncLog(
      client: enc,
      deviceId: 'tablet',
      pathPrefix: layout.prefix,
      localLog: {},
      encode: encodeLog,
      decode: decodeLog,
    );
    expect(merged.keys, unorderedEquals(['a', 'b', 'c']));
  });

  test('copying twice adds no duplicate and loses nothing', () async {
    final remote = _plainRemote();
    final key = await _key(remote, layout);
    Future<MigrationReport> run() => copyToEncrypted(
      store: remote,
      key: key,
      fromPrefix: _old,
      layout: layout,
    );
    await run();
    final first = Map.of(remote.files);
    remote.writes.clear();
    final second = await run();
    expect(second.copied, 0);
    expect(remote.writes, isEmpty);
    expect(remote.files, first);
  });

  test('a later plaintext write by an old build is copied again', () async {
    final remote = _plainRemote();
    final key = await _key(remote, layout);
    await copyToEncrypted(
      store: remote,
      key: key,
      fromPrefix: _old,
      layout: layout,
    );
    remote.files['$_old/pc/log.json'] = encodeLog(
      logOf({'c': 'tea', 'd': 'jam'}, nodeId: 'node-b'),
    );
    final report = await copyToEncrypted(
      store: remote,
      key: key,
      fromPrefix: _old,
      layout: layout,
    );
    expect(report.copied, 1);
    expect(
      await verifyCopy(
        store: remote,
        key: key,
        fromPrefix: _old,
        layout: layout,
      ),
      isTrue,
    );
  });

  test('cleanup refuses before the copy is verified, then deletes', () async {
    final remote = _plainRemote();
    final key = await _key(remote, layout);
    expect(
      await deletePlaintextPrefix(
        store: remote,
        key: key,
        fromPrefix: _old,
        layout: layout,
      ),
      isFalse,
    );
    expect(remote.files['$_old/phone/log.json'], isNotNull);
    await copyToEncrypted(
      store: remote,
      key: key,
      fromPrefix: _old,
      layout: layout,
    );
    expect(
      await deletePlaintextPrefix(
        store: remote,
        key: key,
        fromPrefix: _old,
        layout: layout,
      ),
      isTrue,
    );
    expect(remote.files.keys.where((k) => k.startsWith('$_old/')), isEmpty);
    expect(remote.files['app/notes-e2e/phone/log.json'], isNotNull);
  });

  test('a corrupt source blob is skipped and blocks cleanup', () async {
    final remote = _plainRemote();
    remote.files['$_old/bad/log.json'] = '{oops';
    final key = await _key(remote, layout);
    final report = await copyToEncrypted(
      store: remote,
      key: key,
      fromPrefix: _old,
      layout: layout,
    );
    expect(report.copied, 2);
    expect(report.skipped, ['bad/log.json']);
    expect(
      await deletePlaintextPrefix(
        store: remote,
        key: key,
        fromPrefix: _old,
        layout: layout,
      ),
      isFalse,
    );
  });

  group('slashless prefix (settings-sync)', () {
    final flat = E2eLayout.of('settings-sync');

    test('revs and header stay inside the app node', () {
      expect(flat.prefix, 'settings-sync-e2e');
      expect(flat.revsPath, 'settings-sync-e2e/revs');
      expect(flat.e2ePath, 'settings-sync-e2e/e2e');
    });

    test('old revs and header are not copied as logs', () async {
      final remote = MemoryRemote({
        'settings-sync/phone/log.json': encodeLog(logOf({'a': 'x'})),
        'settings-sync/revs/phone': 'abc',
        'settings-sync/e2e': '{"v":1}',
      });
      final key = await _key(remote, flat);
      final report = await copyToEncrypted(
        store: remote,
        key: key,
        fromPrefix: 'settings-sync',
        layout: flat,
      );
      expect(report.copied, 1);
      expect(report.skipped, isEmpty);
      expect(
        await verifyCopy(
          store: remote,
          key: key,
          fromPrefix: 'settings-sync',
          layout: flat,
        ),
        isTrue,
      );
    });
  });
}
