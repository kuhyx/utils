import 'package:crdt_sync/crdt_sync.dart';
import 'package:test/test.dart';

import 'e2e_fakes.dart';

const _old = 'app/notes';

Future<E2eState> _open(MemoryRemote r, String? pass) => openEncryptedStore(
  store: r,
  oldPrefix: _old,
  readPassphrase: () async => pass,
  params: cheapArgon,
);

void main() {
  test('no passphrase is locked', () async {
    for (final p in [null, '']) {
      final s = await _open(MemoryRemote(), p);
      expect((s as E2eLocked).reason, E2eLockReason.needsPassphrase);
    }
  });

  test('right passphrase copies and is ready; wrong one is locked', () async {
    final r = MemoryRemote({
      '$_old/phone/log.json': encodeLog(logOf({'a': 'milk'})),
    });
    expect(await _open(r, 'pw'), isA<E2eReady>());
    expect(r.files['app/notes-e2e/phone/log.json'], isNot(contains('milk')));
    expect(await _open(r, 'pw'), isA<E2eReady>());
    expect(
      ((await _open(r, 'bad')) as E2eLocked).reason,
      E2eLockReason.wrongKey,
    );
  });

  test('a corrupt header locks as badHeader', () async {
    final r = MemoryRemote({'app/e2e': 'garbage'});
    expect(
      ((await _open(r, 'pw')) as E2eLocked).reason,
      E2eLockReason.badHeader,
    );
  });

  test('a failing copy does not stop the open', () async {
    final r = MemoryRemote();
    r.files['$_old/phone/log.json'] = encodeLog(logOf({'a': 'x'}));
    final failing = _FailingList(r);
    final s = await openEncryptedStore(
      store: failing,
      oldPrefix: _old,
      readPassphrase: () async => 'pw',
      params: cheapArgon,
    );
    expect(s, isA<E2eReady>());
  });
}

class _FailingList extends PlainRemote {
  _FailingList(super.inner);
  @override
  Future<List<String>> listDirectory(String path) =>
      throw StateError('list down');
}
