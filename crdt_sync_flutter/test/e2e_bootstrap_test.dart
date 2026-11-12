import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:crdt_sync_flutter/crdt_sync_flutter.dart';
import 'package:crdt_sync_flutter/testing/fake_secure_storage.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';

const _old = 'todo-sync/notes';
const _cheap = Argon2Params(memoryKiB: 8, iterations: 1, parallelism: 1);

class _Remote implements RemoteStore {
  final files = <String, String>{};
  @override
  Future<List<String>> listDirectory(String path) async => files.keys
      .where((k) => k.startsWith('$path/'))
      .map((k) => k.substring(path.length + 1).split('/').first)
      .toSet()
      .toList();
  @override
  Future<String?> getFileText(String path) async => files[path];
  @override
  Future<void> putFileText(
    String path,
    String text, {
    required String message,
  }) async => files[path] = text;
  @override
  Future<void> deleteFile(String path, {String message = ''}) async =>
      files.remove(path);
  @override
  Future<bool> canAccessRemote() async => true;
  @override
  void close() {}
}

String _log(String title) => jsonEncode({
  'n1': {
    'id': 'n1',
    'fields': {
      'title': [title, '2026-01-01T00:00:00.000Z-0000-a'],
    },
    'deleted': false,
    'deleted_hlc': null,
  },
});

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const storage = FlutterSecureStorage();

  setUp(installFakeSecureStorage);

  test('no passphrase on the device is locked, never plaintext', () async {
    final state = await openEncryptedStoreFromKeystore(
      store: _Remote(),
      oldPrefix: _old,
      params: _cheap,
    );
    expect(state, isA<E2eLocked>());
    expect((state as E2eLocked).reason, E2eLockReason.needsPassphrase);
  });

  test('right passphrase unlocks and copies old plaintext once', () async {
    final remote = _Remote()..files['$_old/phone/log.json'] = _log('milk');
    await saveE2ePassphrase('pw', storage: storage);
    final state = await openEncryptedStoreFromKeystore(
      store: remote,
      oldPrefix: _old,
      params: _cheap,
    );
    expect(state, isA<E2eReady>());
    final layout = E2eLayout.of(_old);
    expect(
      remote.files['${layout.prefix}/phone/log.json'],
      isNot(contains('milk')),
    );
    expect(remote.files['$_old/phone/log.json'], contains('milk'));
    final again = await openEncryptedStoreFromKeystore(
      store: remote,
      oldPrefix: _old,
      params: _cheap,
    );
    expect(again, isA<E2eReady>());
  });

  test('second device with the same passphrase reads the data', () async {
    final remote = _Remote();
    await saveE2ePassphrase('pw', storage: storage);
    final first =
        await openEncryptedStoreFromKeystore(store: remote, oldPrefix: _old, params: _cheap)
            as E2eReady;
    final layout = E2eLayout.of(_old);
    await first.store.putFileText(
      '${layout.prefix}/phone/log.json',
      _log('tea'),
      message: 'm',
    );
    final second =
        await openEncryptedStoreFromKeystore(store: remote, oldPrefix: _old, params: _cheap)
            as E2eReady;
    final text = await second.store.getFileText(
      '${layout.prefix}/phone/log.json',
    );
    expect(text, contains('tea'));
  });

  test('wrong passphrase is locked and merges nothing', () async {
    final remote = _Remote();
    await saveE2ePassphrase('pw', storage: storage);
    await openEncryptedStoreFromKeystore(store: remote, oldPrefix: _old, params: _cheap);
    await saveE2ePassphrase('nope', storage: storage);
    final state = await openEncryptedStoreFromKeystore(
      store: remote,
      oldPrefix: _old,
      params: _cheap,
    );
    expect((state as E2eLocked).reason, E2eLockReason.wrongKey);
  });

  test('clearing the passphrase forgets it', () async {
    await saveE2ePassphrase('pw', storage: storage);
    await clearE2ePassphrase(storage: storage);
    expect(await storage.read(key: kE2ePassphraseKey), isNull);
  });
}
