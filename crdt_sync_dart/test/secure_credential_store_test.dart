/// Tests for the platform-secret-backed credential store.
///
/// The load path degrades to "not signed in" on every failure rather than
/// throwing: an app that threw here would be permanently unable to sync, with
/// no way back short of a reinstall.
library;

import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:test/test.dart';

/// An in-memory stand-in for `flutter_secure_storage`.
class _FakeSecrets {
  final Map<String, String> values = {};
  bool readThrows = false;

  Future<String?> read(String key) async {
    if (readThrows) throw const FormatException('keystore unavailable');
    return values[key];
  }

  Future<void> write(String key, String value) async => values[key] = value;

  Future<void> delete(String key) async => values.remove(key);
}

SecureCredentialStore _store(_FakeSecrets secrets, {String? key}) =>
    SecureCredentialStore(
      read: secrets.read,
      write: secrets.write,
      delete: secrets.delete,
      key: key ?? SecureCredentialStore.defaultKey,
    );

FirebaseCredentials _creds() => FirebaseCredentials(
  idToken: 'id',
  refreshToken: 'refresh',
  expiresAt: DateTime.utc(2026, 8, 5, 7, 45),
);

void main() {
  test('round-trips credentials', () async {
    final secrets = _FakeSecrets();

    await _store(secrets).save(_creds());
    final loaded = await _store(secrets).load();

    expect(loaded, isNotNull);
    expect(loaded!.refreshToken, 'refresh');
    expect(loaded.idToken, 'id');
    expect(loaded.expiresAt, DateTime.utc(2026, 8, 5, 7, 45));
  });

  test('does not collide with the app GitHub token key', () async {
    // Both secrets coexist for the whole mirrored cutover period.
    final secrets = _FakeSecrets();
    secrets.values['sync.token'] = 'github-pat';

    await _store(secrets).save(_creds());

    expect(secrets.values['sync.token'], 'github-pat');
    expect(secrets.values.containsKey('firebase.credentials'), isTrue);
  });

  test('honours a custom key', () async {
    final secrets = _FakeSecrets();

    await _store(secrets, key: 'other').save(_creds());

    expect(secrets.values.containsKey('other'), isTrue);
  });

  test('reports absent credentials as not signed in', () async {
    expect(await _store(_FakeSecrets()).load(), isNull);
  });

  test('treats an empty value as not signed in', () async {
    final secrets = _FakeSecrets()..values['firebase.credentials'] = '';

    expect(await _store(secrets).load(), isNull);
  });

  test('treats corrupt JSON as not signed in', () async {
    final secrets = _FakeSecrets()..values['firebase.credentials'] = '{oops';

    expect(await _store(secrets).load(), isNull);
  });

  test('treats a non-object value as not signed in', () async {
    final secrets = _FakeSecrets()..values['firebase.credentials'] = '[1,2]';

    expect(await _store(secrets).load(), isNull);
  });

  test('treats a wrong-shaped object as not signed in', () async {
    final secrets = _FakeSecrets()
      ..values['firebase.credentials'] = jsonEncode({'id_token': 'only'});

    expect(await _store(secrets).load(), isNull);
  });

  test('treats an unreadable keystore as not signed in', () async {
    final secrets = _FakeSecrets()..readThrows = true;

    expect(await _store(secrets).load(), isNull);
  });

  test('clear removes the credentials', () async {
    final secrets = _FakeSecrets();
    await _store(secrets).save(_creds());

    await _store(secrets).clear();

    expect(secrets.values, isEmpty);
  });
}
