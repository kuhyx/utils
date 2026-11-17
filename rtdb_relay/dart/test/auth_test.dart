import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart'
    show
        FirebaseAuthError,
        FirebaseCredentialStore,
        FirebaseCredentials,
        InMemoryCredentialStore;
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:rtdb_relay/src/auth.dart';

const _config = RelayFirebaseConfig(
  apiKey: 'key',
  databaseUrl: 'https://db',
  syncUid: 'right-uid',
  serverClientId: '',
);

MockClient _idp(String uid) => MockClient(
  (_) async => http.Response(
    jsonEncode({
      'localId': uid,
      'idToken': 'id-1',
      'refreshToken': 'refresh-1',
      'expiresIn': '3600',
    }),
    200,
  ),
);

class _BrokenStore extends InMemoryCredentialStore {
  @override
  Future<FirebaseCredentials?> load() => throw ArgumentError('Uri.base');
}

// The default sign-in: declines when no client id is compiled in.
Future<String?> _google({required String serverClientId}) async =>
    serverClientId.isEmpty ? null : 'g';

RelayAuth _auth(FirebaseCredentialStore store, [http.Client? client]) =>
    RelayAuth(
      config: _config,
      googleToken: _google,
      store: store,
      httpClient: client,
    );

void main() {
  test('right account: session stored, token served', () async {
    final store = InMemoryCredentialStore();
    final auth = _auth(store, _idp('right-uid'));
    expect(await auth.hasSession(), isFalse);
    final out = await auth.signInWithGoogle(tokenFetcher: () async => 'g');
    expect(out, SignInOutcome.signedIn);
    expect(await auth.hasSession(), isTrue);
    expect(await auth.idToken(), 'id-1');
    await auth.signOut();
    expect(await store.load(), isNull);
  });

  test('wrong account throws and stores nothing', () async {
    final store = InMemoryCredentialStore();
    final auth = _auth(store, _idp('second-user'));
    await expectLater(
      auth.signInWithGoogle(tokenFetcher: () async => 'g'),
      throwsA(isA<FirebaseAuthError>()),
    );
    expect(await store.load(), isNull);
  });

  test('cancelled picker and missing client id are not errors', () async {
    final auth = _auth(InMemoryCredentialStore());
    expect(
      await auth.signInWithGoogle(tokenFetcher: () async => null),
      SignInOutcome.cancelled,
    );
    // No client id compiled in: the default fetcher declines.
    expect(await auth.signInWithGoogle(), SignInOutcome.cancelled);
  });

  test('a store that throws an Error reads as signed out', () async {
    final auth = _auth(_BrokenStore());
    expect(await auth.hasSession(), isFalse);
  });

  test('the adopt hook signs in a desktop with no session', () async {
    final store = InMemoryCredentialStore();
    var asked = 0;
    final auth = RelayAuth(
      config: _config,
      googleToken: _google,
      store: store,
      adopt: () async {
        asked++;
        return false;
      },
    );
    expect(await auth.hasSession(), isFalse);
    expect(asked, 1);
  });
}
