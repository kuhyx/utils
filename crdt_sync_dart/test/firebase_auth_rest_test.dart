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

FirebaseCredentials _credentials({
  String idToken = 'id-1',
  String refreshToken = 'refresh-1',
  Duration validFor = const Duration(hours: 1),
}) => FirebaseCredentials(
  idToken: idToken,
  refreshToken: refreshToken,
  expiresAt: _now.add(validFor),
);

void main() {
  group('FirebaseCredentials', () {
    test('round-trips through JSON', () {
      final original = _credentials();
      final restored = FirebaseCredentials.fromJson(original.toJson());
      expect(restored.idToken, original.idToken);
      expect(restored.refreshToken, original.refreshToken);
      expect(restored.expiresAt, original.expiresAt);
    });

    test('is not expired while comfortably inside its lifetime', () {
      expect(_credentials().isExpiredAt(_now), isFalse);
    });

    test('is expired once past expiry', () {
      expect(
        _credentials(validFor: const Duration(minutes: -1)).isExpiredAt(_now),
        isTrue,
      );
    });

    test('is expired inside the refresh skew, before real expiry', () {
      // A tick starting now would outlive a token with 2 minutes left, so it
      // must be treated as already expired.
      expect(
        _credentials(validFor: const Duration(minutes: 2)).isExpiredAt(_now),
        isTrue,
      );
    });
  });

  group('signIn', () {
    test('stores the session returned by identitytoolkit', () async {
      final store = InMemoryCredentialStore();
      final provider = _provider([
        _json(200, {
          'idToken': 'id-1',
          'refreshToken': 'refresh-1',
          'expiresIn': '3600',
        }),
      ], store: store);

      await provider.signIn(email: 'me@example.com', password: 'hunter2');

      final saved = await store.load();
      expect(saved!.idToken, 'id-1');
      expect(saved.refreshToken, 'refresh-1');
      expect(saved.expiresAt, _now.add(const Duration(hours: 1)));
    });

    test('reports Google\'s reason on a rejected password', () async {
      final provider = _provider([
        _json(400, {
          'error': {'message': 'INVALID_LOGIN_CREDENTIALS'},
        }),
      ]);
      expect(
        () => provider.signIn(email: 'me@example.com', password: 'wrong'),
        throwsA(
          isA<FirebaseAuthError>().having(
            (e) => e.message,
            'message',
            contains('INVALID_LOGIN_CREDENTIALS'),
          ),
        ),
      );
    });

    test('reports a string-shaped error body', () async {
      final provider = _provider([
        _json(400, {'error': 'BAD_REQUEST'}),
      ]);
      expect(
        () => provider.signIn(email: 'me@example.com', password: 'x'),
        throwsA(
          isA<FirebaseAuthError>().having(
            (e) => e.message,
            'message',
            contains('BAD_REQUEST'),
          ),
        ),
      );
    });

    test('survives a non-JSON error body', () async {
      final provider = FirebaseTokenProvider(
        apiKey: 'k',
        store: InMemoryCredentialStore(),
        httpClient: http_testing.MockClient(
          (_) async => http.Response('<html>502</html>', 502),
        ),
        clock: () => _now,
      );
      await expectLater(
        () => provider.signIn(email: 'a@b.c', password: 'x'),
        throwsA(isA<FirebaseAuthError>()),
      );
    });

    test('turns a network failure into FirebaseAuthError', () async {
      final provider = _provider([http.ClientException('offline')]);
      expect(
        () => provider.signIn(email: 'a@b.c', password: 'x'),
        throwsA(isA<FirebaseAuthError>()),
      );
    });
  });
}
