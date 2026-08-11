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
