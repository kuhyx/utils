/// openEncryptedStore must not pay Argon2id or a full copy on every tick.
library;

import 'package:crdt_sync/crdt_sync.dart';
import 'package:test/test.dart';

import 'e2e_fakes.dart';

const _old = 'app/notes';

void main() {
  setUp(resetE2eCopyMemo);

  test('a cached key skips Argon2 and still unlocks', () async {
    final remote = MemoryRemote();
    List<int>? cached;
    var derived = 0;
    Future<E2eState> open() => openEncryptedStore(
      store: remote,
      oldPrefix: _old,
      readPassphrase: () async => 'pw',
      params: cheapArgon,
      keyCache: E2eKeyCache(
        read: () async => cached,
        write: (bytes) async => cached = bytes,
      ),
      onDerive: () => derived++,
    );
    expect(await open(), isA<E2eReady>());
    expect(cached, hasLength(32));
    expect(await open(), isA<E2eReady>());
    expect(derived, 1);
  });

  test('a stale cached key falls back to the passphrase', () async {
    final remote = MemoryRemote();
    List<int>? cached = List<int>.filled(32, 9);
    final state = await openEncryptedStore(
      store: remote,
      oldPrefix: _old,
      readPassphrase: () async => 'pw',
      params: cheapArgon,
      keyCache: E2eKeyCache(
        read: () async => cached,
        write: (bytes) async => cached = bytes,
      ),
    );
    expect(state, isA<E2eReady>());
    expect(cached, isNot(List<int>.filled(32, 9)));
  });

  test('the copy reruns only when old revisions change', () async {
    final remote = MemoryRemote({
      '$_old/pc/log.json': encodeLog(logOf({'a': 'x'})),
      'app/revs/pc': 'r1',
    });
    Future<void> open() => openEncryptedStore(
      store: remote,
      oldPrefix: _old,
      readPassphrase: () async => 'pw',
      params: cheapArgon,
    );
    await open();
    remote.reads.clear();
    await open();
    expect(remote.reads.where((p) => p.startsWith('app/notes-e2e/')), isEmpty);
    remote.files['$_old/pc/log.json'] = encodeLog(logOf({'a': 'x', 'b': 'y'}));
    remote.files['app/revs/pc'] = 'r2';
    await open();
    final state =
        await openEncryptedStore(
              store: remote,
              oldPrefix: _old,
              readPassphrase: () async => 'pw',
              params: cheapArgon,
            )
            as E2eReady;
    final text = await state.store.getFileText('app/notes-e2e/pc/log.json');
    expect(decodeLog(text!).keys, unorderedEquals(['a', 'b']));
  });

  test('bulk reads of a data dir come back decrypted', () async {
    final remote = MemoryRemote();
    final state =
        await openEncryptedStore(
              store: remote,
              oldPrefix: _old,
              readPassphrase: () async => 'pw',
              params: cheapArgon,
            )
            as E2eReady;
    final log = encodeLog(logOf({'k': 'secret'}));
    await state.store.putFileText('app/notes-e2e/k1', log, message: 'm');
    expect(remote.files['app/notes-e2e/k1'], isNot(contains('secret')));
    final map = await state.store.getStringMap('app/notes-e2e');
    expect(map['k1'], log);
  });
}
