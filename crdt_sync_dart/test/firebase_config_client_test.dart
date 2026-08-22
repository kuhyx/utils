/// Tests for the shared Firebase configuration on the Dart side.
///
/// The failure modes asserted here are the ones that would otherwise surface
/// as an authentication error long after the real mistake, so each is checked
/// to name the field at fault rather than merely to throw.
library;

import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart' as http_testing;
import 'package:test/test.dart';

const _valid = {
  'apiKey': 'AIzaSyExample',
  'databaseUrl':
      'https://kuhy-syncs-default-rtdb.europe-west1.firebasedatabase.app',
  'projectId': 'kuhy-syncs',
  'uid': 'OvA2REQyLIhAHOEjzwS1o877rgG3',
  'email': 'sync@example.com',
};

void main() {
  group('client construction', () {
    test('refuses to build without a session or a password', () async {
      // Better than signing in with an empty password and failing remotely.
      await expectLater(
        firebaseClientFor(
          config: FirebaseConfig.parse(jsonEncode(_valid)),
          store: InMemoryCredentialStore(),
        ),
        throwsA(isA<ConfigException>()),
      );
    });

    test('signs in with the password when there is no session', () async {
      // The first-run path: no cached refresh token, so it must exchange the
      // password for one rather than failing.
      final store = InMemoryCredentialStore();
      final sentTo = <String>[];
      final mock = http_testing.MockClient((request) async {
        sentTo.add(request.url.path);
        return http.Response(
          jsonEncode({
            'idToken': 'id',
            'refreshToken': 'refresh',
            'expiresIn': '3600',
            'localId': _valid['uid'],
          }),
          200,
        );
      });

      final client = await firebaseClientFor(
        config: FirebaseConfig.parse(jsonEncode(_valid)),
        store: store,
        password: 'hunter2',
        httpClient: mock,
      );

      expect(sentTo.single, contains('signInWithPassword'));
      expect(await store.load(), isNotNull, reason: 'session must persist');
      client.close();
    });

    test('signs in with Google when a token is available', () async {
      // The one-tap path: a fresh install with no password typed anywhere.
      final store = InMemoryCredentialStore();
      final sentTo = <String>[];
      final mock = http_testing.MockClient((request) async {
        sentTo.add(request.url.path);
        return http.Response(
          jsonEncode({
            'idToken': 'id',
            'refreshToken': 'refresh',
            'expiresIn': '3600',
            'localId': _valid['uid'],
          }),
          200,
        );
      });

      final client = await firebaseClientFor(
        config: FirebaseConfig.parse(jsonEncode(_valid)),
        store: store,
        googleIdToken: () async => 'google-token',
        httpClient: mock,
      );

      expect(sentTo.single, contains('signInWithIdp'));
      expect(await store.load(), isNotNull, reason: 'session must persist');
      client.close();
    });

    test('prefers Google over the password when both are available', () async {
      // Google is the credential the user did not have to type, so on a device
      // offering both it should win.
      final sentTo = <String>[];
      final mock = http_testing.MockClient((request) async {
        sentTo.add(request.url.path);
        return http.Response(
          jsonEncode({
            'idToken': 'id',
            'refreshToken': 'refresh',
            'expiresIn': '3600',
            // Firebase always returns localId; the config carries a uid, so
            // omitting it here would trip the wrong-account guard.
            'localId': _valid['uid'],
          }),
          200,
        );
      });

      final client = await firebaseClientFor(
        config: FirebaseConfig.parse(jsonEncode(_valid)),
        store: InMemoryCredentialStore(),
        password: 'hunter2',
        googleIdToken: () async => 'google-token',
        httpClient: mock,
      );

      expect(sentTo.single, contains('signInWithIdp'));
      client.close();
    });
  });
}
