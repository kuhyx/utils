import 'dart:convert';
import 'dart:io';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:crdt_sync_flutter/crdt_sync_flutter.dart';
import 'package:crdt_sync_flutter/testing/fake_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const routes = WrapperRoutes(
    credentialsPath: '/sync-credentials',
    accountPath: '/sync-account',
  );
  final base = Uri.parse('http://127.0.0.1:8080/');

  group('loadAccount', () {
    test('returns the stored account without touching the wrapper', () async {
      const stored = FirebaseAccount(email: 'a@b.c', password: 'pw');
      installFakeSecureStorage(
        initial: {kAccountKey: stored.toJsonString()},
      );
      var requests = 0;
      final account = await loadAccount(
        routes: routes,
        base: base,
        httpClient: MockClient((_) async {
          requests += 1;
          return http.Response('', 404);
        }),
      );

      expect(account?.email, 'a@b.c');
      expect(requests, 0, reason: 'the keystore already answered');
    });

    test('returns null with no account and no routes', () async {
      installFakeSecureStorage();
      expect(await loadAccount(), isNull);
    });

    test('honours the opt-out flag instead of re-provisioning', () async {
      installFakeSecureStorage(initial: {kOptOutKey: 'true'});
      var requests = 0;
      final account = await loadAccount(
        routes: routes,
        base: base,
        httpClient: MockClient((_) async {
          requests += 1;
          return http.Response('', 200);
        }),
      );

      expect(account, isNull);
      expect(requests, 0, reason: 'disconnect must stick');
    });

    test('adopts a seeded session and persists it', () async {
      installFakeSecureStorage();
      final body = jsonEncode({
        'id_token': 'id',
        'refresh_token': 'refresh',
        'expires_at': DateTime.now()
            .add(const Duration(hours: 1))
            .toIso8601String(),
        'email': 'seeded@b.c',
      });
      final account = await loadAccount(
        routes: routes,
        base: base,
        httpClient: MockClient(
          (request) async => request.url.path == '/sync-credentials'
              ? http.Response(body, 200)
              : http.Response('', 404),
        ),
      );

      expect(account?.email, 'seeded@b.c');
      expect(account?.password, isEmpty);
      // Persisted, so the route is consulted once rather than forever.
      expect((await storedAccount())?.email, 'seeded@b.c');
    });

    test('ignores a seeded body missing a required field', () async {
      installFakeSecureStorage();
      final account = await loadAccount(
        routes: routes,
        base: base,
        httpClient: MockClient(
          (_) async => http.Response(jsonEncode({'id_token': 'id'}), 200),
        ),
      );

      expect(account, isNull);
    });

    test('ignores a seeded body that is not a JSON object', () async {
      installFakeSecureStorage();
      final account = await loadAccount(
        routes: routes,
        base: base,
        httpClient: MockClient((_) async => http.Response('[]', 200)),
      );

      expect(account, isNull);
    });

    test('skips the legacy route when the app declares none', () async {
      installFakeSecureStorage();
      var paths = <String>[];
      final account = await loadAccount(
        routes: const WrapperRoutes(credentialsPath: '/sync-credentials'),
        base: base,
        httpClient: MockClient((request) async {
          paths.add(request.url.path);
          return http.Response('', 404);
        }),
      );

      expect(account, isNull);
      expect(paths, ['/sync-credentials']);
    });

    test('reports not-configured when the keystore itself throws', () async {
      installFakeSecureStorage(throwing: true);
      expect(await loadAccount(routes: routes, base: base), isNull);
    });

    test('falls back to the legacy route and persists what it finds', () async {
      // The un-reseeded machine: no seeded session, but the wrapper still
      // serves an email/password pair from ~/.config/crdt-sync.
      installFakeSecureStorage();
      final account = await loadAccount(
        routes: routes,
        base: base,
        httpClient: MockClient(
          (request) async => request.url.path == '/sync-account'
              ? http.Response(
                  jsonEncode({'email': 'legacy@b.c', 'password': 'pw'}),
                  200,
                )
              : http.Response('', 404),
        ),
      );

      expect(account?.email, 'legacy@b.c');
      // Written through, so the route is consulted once and not forever.
      expect((await storedAccount())?.password, 'pw');
    });

    test('defaults to Uri.base and a real client with no wrapper', () async {
      // The production call shape: no base, no injected client. Under
      // `flutter test` Uri.base is a file:// URL with no host, so resolving
      // the route raises an ArgumentError -- an Error, not an Exception,
      // which is exactly the Android case the broad catch exists for.
      installFakeSecureStorage();

      expect(await loadAccount(routes: routes), isNull);
    });

    test('survives a wrapper that drops the connection', () async {
      installFakeSecureStorage();
      final account = await loadAccount(
        routes: routes,
        base: base,
        httpClient: MockClient((_) async => throw const SocketException('x')),
      );

      expect(account, isNull);
    });
  });

  group('account lifecycle', () {
    test('saveAccount then storedAccount round-trips', () async {
      installFakeSecureStorage();
      await saveAccount(const FirebaseAccount(email: 'x@y.z', password: 'p'));
      expect((await storedAccount())?.password, 'p');
    });

    test('clearAccount forgets the account and sets the opt-out', () async {
      installFakeSecureStorage();
      await saveAccount(const FirebaseAccount(email: 'x@y.z', password: 'p'));
      await clearAccount();

      expect(await storedAccount(), isNull);
      // The flag is what stops the wrapper silently re-adopting it.
      expect(await loadAccount(routes: routes, base: base), isNull);
    });

    test('clearAccountMarkerOnly leaves re-provisioning possible', () async {
      installFakeSecureStorage();
      await saveAccount(const FirebaseAccount(email: 'x@y.z', password: 'p'));
      await clearAccountMarkerOnly();

      expect(await storedAccount(), isNull);
      final body = jsonEncode({
        'id_token': 'id',
        'refresh_token': 'refresh',
        'expires_at': DateTime.now()
            .add(const Duration(hours: 1))
            .toIso8601String(),
        'email': 'again@b.c',
      });
      final account = await loadAccount(
        routes: routes,
        base: base,
        httpClient: MockClient((_) async => http.Response(body, 200)),
      );
      expect(account?.email, 'again@b.c');
    });
  });
}
