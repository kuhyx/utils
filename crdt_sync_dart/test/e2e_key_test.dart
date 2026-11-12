/// Passphrase -> key, the clear header beside the data, and the open gate.
library;

import 'dart:convert';
import 'dart:math';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:test/test.dart';

import 'e2e_fakes.dart';

const _prefix = 'todo-sync/notes';
const _headerPath = 'todo-sync/e2e';

Future<E2eKey> _unlock(MemoryRemote remote, String passphrase) => unlockE2e(
  store: remote,
  pathPrefix: _prefix,
  passphrase: passphrase,
  params: cheapArgon,
  random: Random(1),
);

void main() {
  test('the header sits beside the device dirs, not among them', () {
    expect(defaultE2ePath(_prefix), _headerPath);
    expect(defaultE2ePath('wake-alarm'), 'wake-alarm/e2e');
  });

  test(
    'first unlock writes a clear header with salt, params and check',
    () async {
      final remote = MemoryRemote();
      await _unlock(remote, 'correct horse');
      final header = jsonDecode(remote.files[_headerPath]!) as Map;
      expect(header['v'], 1);
      expect(header['kdf'], 'argon2id');
      expect(base64.decode(header['salt'] as String), hasLength(16));
      expect(header['m'], 8);
      expect(header['t'], 1);
      expect(header['p'], 1);
      expect(header['check'], isA<String>());
      expect(remote.files[_headerPath], isNot(contains('correct horse')));
    },
  );

  test('the same passphrase on another device yields the same key', () async {
    final remote = MemoryRemote();
    final a = await _unlock(remote, 'pw');
    final b = await unlockE2e(
      store: remote,
      pathPrefix: _prefix,
      passphrase: 'pw',
      random: Random(99),
    );
    expect(b.bytes, a.bytes);
    expect(remote.writes, [_headerPath]);
  });

  test('a wrong passphrase is refused before anything is written', () async {
    final remote = MemoryRemote();
    await _unlock(remote, 'pw');
    remote.writes.clear();
    await expectLater(
      _unlock(remote, 'not pw'),
      throwsA(isA<E2eWrongPassphraseError>()),
    );
    expect(remote.writes, isEmpty);
  });

  test('a setup race derives from the header that won', () async {
    final winner = MemoryRemote();
    await unlockE2e(
      store: winner,
      pathPrefix: _prefix,
      passphrase: 'pw',
      params: cheapArgon,
      random: Random(5),
    );
    final remote = MemoryRemote()
      ..scriptedReads[_headerPath] = [null, winner.files[_headerPath]];
    final key = await _unlock(remote, 'pw');
    final expected = await _unlock(winner, 'pw');
    expect(key.bytes, expected.bytes);
  });

  test('an empty passphrase is refused', () {
    expect(() => _unlock(MemoryRemote(), ''), throwsArgumentError);
  });

  test('a corrupt or newer header is refused, never overwritten', () async {
    for (final bad in ['nope', '[]', '{"v":2}', '{"v":1,"kdf":"scrypt"}']) {
      final remote = MemoryRemote({_headerPath: bad});
      await expectLater(
        _unlock(remote, 'pw'),
        throwsA(isA<E2eHeaderError>()),
        reason: bad,
      );
      expect(remote.files[_headerPath], bad);
    }
  });

  test('E2eKey.fromBytes round-trips a cached key', () async {
    final key = await _unlock(MemoryRemote(), 'pw');
    final cached = await E2eKey.fromBytes(
      base64.decode(base64.encode(key.bytes)),
    );
    expect(cached.bytes, key.bytes);
    expect(await cached.revision('x'), await key.revision('x'));
    expect(() => E2eKey.fromBytes(const [1]), throwsArgumentError);
  });

  test('revision is keyed: not sha256, and differs across keys', () async {
    final a = await _unlock(MemoryRemote(), 'a');
    final b = await _unlock(MemoryRemote(), 'b');
    expect(await a.revision('{}'), isNot(revisionOf('{}')));
    expect(await a.revision('{}'), isNot(await b.revision('{}')));
    expect(await a.revision('{}'), await a.revision('{}'));
  });

  test('errors read as themselves', () {
    expect(E2eWrongPassphraseError().toString(), contains('passphrase'));
    expect(E2eHeaderError('x').toString(), 'E2eHeaderError: x');
  });

  group('openE2e', () {
    test('no header and no key: off, plaintext sync allowed', () async {
      final state = await openE2e(store: MemoryRemote(), pathPrefix: _prefix);
      expect(state, isA<E2eOff>());
    });

    test('header but no key: locked, needs the passphrase', () async {
      final remote = MemoryRemote();
      await _unlock(remote, 'pw');
      final state = await openE2e(store: remote, pathPrefix: _prefix);
      expect(state, isA<E2eLocked>());
      expect((state as E2eLocked).reason, E2eLockReason.needsPassphrase);
    });

    test('a cached key the header rejects: locked, wrong key', () async {
      final remote = MemoryRemote();
      await _unlock(remote, 'pw');
      final stale = await _unlock(MemoryRemote(), 'old');
      final state = await openE2e(
        store: remote,
        pathPrefix: _prefix,
        key: stale,
      );
      expect((state as E2eLocked).reason, E2eLockReason.wrongKey);
    });

    test('a cached key with the header gone: locked, wrong key', () async {
      final key = await _unlock(MemoryRemote(), 'pw');
      final state = await openE2e(
        store: MemoryRemote(),
        pathPrefix: _prefix,
        key: key,
      );
      expect((state as E2eLocked).reason, E2eLockReason.wrongKey);
    });

    test('a corrupt header: locked, unreadable header', () async {
      final state = await openE2e(
        store: MemoryRemote({_headerPath: 'garbage'}),
        pathPrefix: _prefix,
      );
      expect((state as E2eLocked).reason, E2eLockReason.badHeader);
    });

    test('a matching key: ready with an encrypting store', () async {
      final remote = MemoryRemote();
      final key = await _unlock(remote, 'pw');
      final state = await openE2e(store: remote, pathPrefix: _prefix, key: key);
      expect((state as E2eReady).store, isA<EncryptingStore>());
    });
  });

  test('recommended params meet the OWASP Argon2id floor', () {
    expect(Argon2Params.recommended.memoryKiB, greaterThanOrEqualTo(19456));
    expect(Argon2Params.recommended.iterations, greaterThanOrEqualTo(2));
  });
}
