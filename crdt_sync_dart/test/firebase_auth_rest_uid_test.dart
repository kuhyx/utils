import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart' as http_testing;
import 'package:test/test.dart';

/// A fixed "now" so token expiry is deterministic rather than wall-clock.
final _now = DateTime.utc(2026, 8, 3, 12);

http.Response _json(int statusCode, Object body) =>
    http.Response(jsonEncode(body), statusCode);

/// Builds a provider whose POSTs return [responses] in call order (each
/// either an [http.Response] or a thrown [http.ClientException]).
FirebaseTokenProvider _provider(
  List<Object> responses, {
  FirebaseCredentialStore? store,
  DateTime? now,
}) {
  var index = 0;
  final mock = http_testing.MockClient((request) async {
    final response = responses[index];
    index++;
    if (response is http.ClientException) throw response;
    return response as http.Response;
  });
  return FirebaseTokenProvider(
    apiKey: 'fake-api-key',
    store: store ?? InMemoryCredentialStore(),
    httpClient: mock,
    clock: () => now ?? _now,
  );
}

void main() {
  group('signInWithGoogle uid verification', () {
    test('rejects a session for a uid other than the expected one', () async {
      // The mis-tapped-account-picker case. signInWithIdp signs in OR SIGNS
      // UP, so an unlinked Google identity is accepted as a brand-new user
      // rather than refused. Without this check the device would store that
      // session and then be denied every read and write, permanently.
      final store = InMemoryCredentialStore();
      final provider = _provider([
        _json(200, {
          'idToken': 'id-g',
          'refreshToken': 'refresh-g',
          'expiresIn': '3600',
          'localId': 'some-other-uid',
        }),
      ], store: store);

      await expectLater(
        () => provider.signInWithGoogle(
          idToken: 'token-for-the-wrong-account',
          expectedUid: 'the-right-uid',
        ),
        throwsA(
          isA<FirebaseAuthError>().having(
            (e) => e.message,
            'message',
            allOf(contains('some-other-uid'), contains('the-right-uid')),
          ),
        ),
      );
      expect(
        await store.load(),
        isNull,
        reason: 'a wrong-account session must not persist',
      );
      expect(await provider.hasSession(), isFalse);
    });

    test('accepts a session whose uid matches the expected one', () async {
      final store = InMemoryCredentialStore();
      final provider = _provider([
        _json(200, {
          'idToken': 'id-g',
          'refreshToken': 'refresh-g',
          'expiresIn': '3600',
          'localId': 'the-right-uid',
        }),
      ], store: store);

      await provider.signInWithGoogle(
        idToken: 'token',
        expectedUid: 'the-right-uid',
      );

      expect((await store.load())!.idToken, 'id-g');
    });

    test('skips the uid check when no uid is expected', () async {
      // FirebaseProject.configFor leaves uid empty on the app path; comparing
      // against '' would otherwise fail every sign-in.
      final store = InMemoryCredentialStore();
      final provider = _provider([
        _json(200, {
          'idToken': 'id-g',
          'refreshToken': 'refresh-g',
          'expiresIn': '3600',
          'localId': 'whatever-uid',
        }),
      ], store: store);

      await provider.signInWithGoogle(idToken: 'token', expectedUid: '');

      expect((await store.load())!.idToken, 'id-g');
    });

    test('its session refreshes like a password session', () async {
      // signInWithIdp returns the same refresh-token shape as
      // signInWithPassword, which is why the refresh path needed no changes.
      final store = InMemoryCredentialStore();
      final provider = _provider([
        _json(200, {
          'idToken': 'id-g',
          'refreshToken': 'refresh-g',
          // Already inside the refresh skew, so the next read must refresh.
          'expiresIn': '60',
        }),
        _json(200, {
          'id_token': 'id-g2',
          'refresh_token': 'refresh-g2',
          'expires_in': '3600',
        }),
      ], store: store);

      await provider.signInWithGoogle(idToken: 'google-token');
      expect(await provider.idToken(), 'id-g2');
      expect((await store.load())!.refreshToken, 'refresh-g2');
    });
  });
}
