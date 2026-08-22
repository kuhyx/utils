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
  group('signInWithGoogle', () {
    test('stores the session returned by identitytoolkit', () async {
      final store = InMemoryCredentialStore();
      final provider = _provider([
        _json(200, {
          'idToken': 'id-g',
          'refreshToken': 'refresh-g',
          'expiresIn': '3600',
        }),
      ], store: store);

      await provider.signInWithGoogle(idToken: 'google-token');

      final saved = await store.load();
      expect(saved!.idToken, 'id-g');
      expect(saved.refreshToken, 'refresh-g');
      expect(saved.expiresAt, _now.add(const Duration(hours: 1)));
    });

    test('posts the IdP credential form-encoded to signInWithIdp', () async {
      // The identitytoolkit quirk worth pinning: the Google token travels in a
      // form-encoded `postBody` string, not as a JSON field. Getting this
      // wrong returns INVALID_IDP_RESPONSE, which reads like a bad token.
      late http.Request captured;
      final provider = FirebaseTokenProvider(
        apiKey: 'fake-api-key',
        store: InMemoryCredentialStore(),
        httpClient: http_testing.MockClient((request) async {
          captured = request;
          return _json(200, {
            'idToken': 'id-g',
            'refreshToken': 'refresh-g',
            'expiresIn': '3600',
          });
        }),
        clock: () => _now,
      );

      await provider.signInWithGoogle(idToken: 'google-token');

      expect(captured.url.path, contains('accounts:signInWithIdp'));
      final body = jsonDecode(captured.body) as Map<String, dynamic>;
      expect(body['postBody'], 'id_token=google-token&providerId=google.com');
      expect(body['returnSecureToken'], isTrue);
    });

    test('reports Google\'s reason on a rejected token', () async {
      final provider = _provider([
        _json(400, {
          'error': {'message': 'INVALID_IDP_RESPONSE'},
        }),
      ]);
      expect(
        () => provider.signInWithGoogle(idToken: 'stale-token'),
        throwsA(
          isA<FirebaseAuthError>().having(
            (e) => e.message,
            'message',
            contains('INVALID_IDP_RESPONSE'),
          ),
        ),
      );
    });

    test('leaves no session stored when the token is rejected', () async {
      // A failed Google sign-in must not look like a signed-in device: the
      // next idToken() has to fail loudly rather than serve a stale token.
      final store = InMemoryCredentialStore();
      final provider = _provider([
        _json(400, {
          'error': {'message': 'INVALID_IDP_RESPONSE'},
        }),
      ], store: store);

      await expectLater(
        () => provider.signInWithGoogle(idToken: 'bad'),
        throwsA(isA<FirebaseAuthError>()),
      );
      expect(await store.load(), isNull);
      expect(await provider.hasSession(), isFalse);
    });

    test('returns the email Firebase reports', () async {
      // A fresh install knows no email until Firebase answers with one, so
      // this return value is what lets the device store its account. Reading
      // the email from anywhere on-device instead would store an empty one.
      final provider = _provider([
        _json(200, {
          'idToken': 'id-g',
          'refreshToken': 'refresh-g',
          'expiresIn': '3600',
          'email': 'signed-in@example.com',
        }),
      ]);

      expect(
        await provider.signInWithGoogle(idToken: 'token'),
        'signed-in@example.com',
      );
    });

    test('returns null when the response carries no email', () async {
      // Not fatal: the session is still valid, so sign-in succeeds and the
      // caller simply has no address to display.
      final provider = _provider([
        _json(200, {
          'idToken': 'id-g',
          'refreshToken': 'refresh-g',
          'expiresIn': '3600',
        }),
      ]);

      expect(await provider.signInWithGoogle(idToken: 'token'), isNull);
    });
  });
}
