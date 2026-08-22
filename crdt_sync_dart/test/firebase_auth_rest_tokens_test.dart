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
  group('idToken', () {
    test('fails loudly when no session is stored', () {
      // Never returns null or a stale token: a sync that quietly stops
      // syncing is exactly the failure mode being designed out.
      expect(
        _provider([]).idToken,
        throwsA(
          isA<FirebaseAuthError>().having(
            (e) => e.message,
            'message',
            contains('not signed in'),
          ),
        ),
      );
    });

    test('returns the stored token without a network call', () async {
      // An empty response list means any HTTP call would throw a range error.
      final provider = _provider(
        [],
        store: InMemoryCredentialStore(_credentials()),
      );
      expect(await provider.idToken(), 'id-1');
    });

    test(
      'refreshes an expired token and persists the rotated refresh token',
      () async {
        final store = InMemoryCredentialStore(
          _credentials(validFor: const Duration(minutes: -5)),
        );
        final provider = _provider([
          _json(200, {
            'id_token': 'id-2',
            'refresh_token': 'refresh-2',
            'expires_in': '3600',
          }),
        ], store: store);

        expect(await provider.idToken(), 'id-2');
        final saved = await store.load();
        expect(saved!.refreshToken, 'refresh-2');
      },
    );

    test('fails loudly when the refresh token has been revoked', () async {
      final provider = _provider(
        [
          _json(400, {
            'error': {'message': 'TOKEN_EXPIRED'},
          }),
        ],
        store: InMemoryCredentialStore(
          _credentials(validFor: const Duration(minutes: -5)),
        ),
      );
      expect(
        provider.idToken,
        throwsA(
          isA<FirebaseAuthError>().having(
            (e) => e.message,
            'message',
            contains('TOKEN_EXPIRED'),
          ),
        ),
      );
    });
  });

  group('session lifecycle', () {
    test('hasSession is false before sign-in and true after', () async {
      final store = InMemoryCredentialStore();
      final provider = _provider([
        _json(200, {
          'idToken': 'id-1',
          'refreshToken': 'refresh-1',
          'expiresIn': '3600',
        }),
      ], store: store);

      expect(await provider.hasSession(), isFalse);
      await provider.signIn(email: 'a@b.c', password: 'x');
      expect(await provider.hasSession(), isTrue);
    });

    test('signOut clears the store so the next idToken fails', () async {
      final provider = _provider(
        [],
        store: InMemoryCredentialStore(_credentials()),
      );
      expect(await provider.idToken(), 'id-1');
      await provider.signOut();
      expect(provider.idToken, throwsA(isA<FirebaseAuthError>()));
    });

    test('close releases the HTTP client', () {
      expect(_provider([]).close, returnsNormally);
    });
  });

  group('a refresh token the server rejects', () {
    // Regression: hasSession() was a presence check, so a revoked token still
    // read as "Connected" while every sync died with TOKEN_EXPIRED. Observed
    // on the desktop todo build on 2026-08-11.
    test(
      'is cleared, so hasSession stops claiming the device is connected',
      () async {
        final store = InMemoryCredentialStore(
          _credentials(validFor: const Duration(seconds: -1)),
        );
        final provider = _provider([
          _json(400, {
            'error': {'message': 'TOKEN_EXPIRED'},
          }),
        ], store: store);

        await expectLater(provider.idToken, throwsA(isA<FirebaseAuthError>()));
        expect(
          await provider.hasSession(),
          isFalse,
          reason: 'a revoked session must not keep reporting as connected',
        );
        expect(await store.load(), isNull);
      },
    );

    test('survives a network error, which is transient', () async {
      // The opposite failure: signing out whenever the wifi drops would need a
      // manual sign-in on every device to recover.
      final store = InMemoryCredentialStore(
        _credentials(validFor: const Duration(seconds: -1)),
      );
      final provider = _provider([
        http.ClientException('connection reset'),
      ], store: store);

      await expectLater(provider.idToken, throwsA(isA<FirebaseAuthError>()));
      expect(
        await provider.hasSession(),
        isTrue,
        reason: 'a transient failure must not discard a good refresh token',
      );
      expect(await store.load(), isNotNull);
    });

    test('survives a 5xx, which is also transient', () async {
      final store = InMemoryCredentialStore(
        _credentials(validFor: const Duration(seconds: -1)),
      );
      final provider = _provider([
        _json(503, {
          'error': {'message': 'SERVICE_UNAVAILABLE'},
        }),
      ], store: store);

      await expectLater(provider.idToken, throwsA(isA<FirebaseAuthError>()));
      expect(await provider.hasSession(), isTrue);
    });
  });
}
