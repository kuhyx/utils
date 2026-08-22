import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:crdt_sync_flutter/crdt_sync_flutter.dart';
import 'package:crdt_sync_flutter/testing/fake_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

const _app = SyncApp(
  project: FirebaseProject(
    apiKey: 'test-key',
    databaseUrl: 'https://example-rtdb.europe-west1.firebasedatabase.app',
  ),
  expectedUid: 'uid-123',
);

/// A live session, so no sign-in round trip is attempted.
String _session({Duration valid = const Duration(hours: 1)}) => jsonEncode({
  'id_token': 'id',
  'refresh_token': 'refresh',
  'expires_at': DateTime.now().add(valid).toIso8601String(),
});

/// Answers Identity Toolkit as though [email] signed in.
MockClient _signsInAs(String? email, {String uid = 'uid-123'}) => MockClient(
  (_) async => http.Response(
    jsonEncode({
      'idToken': 'id',
      'refreshToken': 'refresh',
      'expiresIn': '3600',
      'email': email,
      'localId': uid,
    }),
    200,
  ),
);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('openSync', () {
    test('returns null when nothing is configured', () async {
      installFakeSecureStorage();
      expect(await openSync(_app), isNull);
    });

    test('recovers a client from a stored session with no marker', () async {
      // The state a Google sign-in used to leave behind. The refresh token is
      // the credential, so this device can sync even with no account blob.
      installFakeSecureStorage(
        initial: {SecureCredentialStore.defaultKey: _session()},
      );

      final client = await openSync(_app);

      expect(client, isNotNull);
      client?.close();
    });

    test('uses a stored account with a live session', () async {
      installFakeSecureStorage(
        initial: {
          kAccountKey: const FirebaseAccount(
            email: 'a@b.c',
            password: 'pw',
          ).toJsonString(),
          SecureCredentialStore.defaultKey: _session(),
        },
      );

      final client = await openSync(_app);

      expect(client, isNotNull);
      client?.close();
    });

    test('treats a Google account (empty password) as configured', () async {
      // The regression this package's crdt_sync bump fixed: the marker parses
      // now, so this takes the account path rather than falling through.
      installFakeSecureStorage(
        initial: {
          kAccountKey: const FirebaseAccount(
            email: 'g@b.c',
            password: '',
          ).toJsonString(),
          SecureCredentialStore.defaultKey: _session(),
        },
      );

      expect(await storedAccount(), isNotNull);
      final client = await openSync(_app);

      expect(client, isNotNull);
      client?.close();
    });
  });

  group('signInWithGoogle', () {
    test('returns null when the user dismisses the picker', () async {
      installFakeSecureStorage();

      final client = await signInWithGoogle(
        _app,
        tokenFetcher: () async => null,
      );

      expect(client, isNull);
      expect(await storedAccount(), isNull);
    });

    test('persists the email Firebase reports', () async {
      installFakeSecureStorage();

      final client = await signInWithGoogle(
        _app,
        tokenFetcher: () async => 'google-token',
        httpClient: _signsInAs('reported@b.c'),
      );

      expect(client, isNotNull);
      expect((await storedAccount())?.email, 'reported@b.c');
      client?.close();
    });

    test('stays configured when Google hides the address', () async {
      // signInWithIdp omits `email` for a hidden address, so the marker is
      // written as `email: ''` -- which `tryParse` rejects, deliberately: an
      // address-less marker carries no identity. The device is still fully
      // signed in, because the refresh token is the credential and it is
      // durable. This is exactly why openSync falls back to stored-session
      // recovery instead of trusting the marker.
      installFakeSecureStorage();

      final client = await signInWithGoogle(
        _app,
        tokenFetcher: () async => 'google-token',
        httpClient: _signsInAs(null),
      );
      client?.close();

      expect(client, isNotNull);
      expect(await isSyncConfigured(_app), isTrue);
      final recovered = await openSync(_app);
      expect(recovered, isNotNull, reason: 'the session alone is enough');
      recovered?.close();
    });

    test('throws when Google resolves to the wrong uid', () async {
      installFakeSecureStorage();

      await expectLater(
        signInWithGoogle(
          _app,
          tokenFetcher: () async => 'google-token',
          httpClient: _signsInAs('a@b.c', uid: 'someone-else'),
        ),
        throwsA(isA<FirebaseAuthError>()),
      );
    });
  });

  group('isSyncConfigured', () {
    test('is true with a live session', () async {
      installFakeSecureStorage(
        initial: {SecureCredentialStore.defaultKey: _session()},
      );
      expect(await isSyncConfigured(_app), isTrue);
    });

    test('is false with nothing stored', () async {
      installFakeSecureStorage();
      expect(await isSyncConfigured(_app), isFalse);
    });

    test('drops a marker whose session is gone', () async {
      // A revoked refresh token clears the session; a marker left behind
      // would report "Connected" while every sync failed.
      installFakeSecureStorage(
        initial: {
          kAccountKey: const FirebaseAccount(
            email: 'a@b.c',
            password: 'pw',
          ).toJsonString(),
        },
      );

      expect(await isSyncConfigured(_app), isFalse);
      expect(
        await storedAccount(),
        isNull,
        reason: 'the stale half is dropped so settings offers a sign-in',
      );
    });

    test('reports not-configured when the keystore throws', () async {
      installFakeSecureStorage(throwing: true);
      expect(await isSyncConfigured(_app), isFalse);
    });
  });

  test('openSync survives a keystore that cannot be read at all', () async {
    // A Linux box with no libsecret: every keystore call raises. There is no
    // account and no session to be had, so this device simply does not sync
    // -- but it must not take the caller down with it.
    installFakeSecureStorage(throwing: true);

    expect(await openSync(_app), isNull);
  });
}
