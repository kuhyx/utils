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

/// A [RemoteStore] that does nothing, standing in for the GitHub client.
class _StubRemote implements RemoteStore {
  @override
  Future<List<String>> listDirectory(String path) async => [];

  @override
  Future<String?> getFileText(String path) async => null;

  @override
  Future<void> putFileText(
    String path,
    String text, {
    required String message,
  }) async {}

  @override
  Future<void> deleteFile(String path, {String message = ''}) async {}

  @override
  Future<bool> canAccessRemote() async => true;

  @override
  void close() {}
}

void main() {
  group('FirebaseConfig', () {
    test('parses a valid config', () {
      final config = FirebaseConfig.parse(jsonEncode(_valid));

      expect(config.apiKey, 'AIzaSyExample');
      expect(config.projectId, 'kuhy-syncs');
      expect(config.uid, 'OvA2REQyLIhAHOEjzwS1o877rgG3');
      expect(config.email, 'sync@example.com');
      expect(config.databaseUrl, endsWith('europe-west1.firebasedatabase.app'));
    });

    test('ignores the scaffold comment keys', () {
      final annotated = {..._valid, '_comment_apiKey': 'where to find it'};

      expect(
        FirebaseConfig.parse(jsonEncode(annotated)).apiKey,
        'AIzaSyExample',
      );
    });

    test('agrees with the Python side on the field names', () {
      // Both languages read the same file; a rename on one side only would
      // break the other silently.
      final config = FirebaseConfig.parse(jsonEncode(_valid));

      expect(config.databaseUrl, _valid['databaseUrl']);
      expect(config.uid, _valid['uid']);
    });

    for (final field in _valid.keys) {
      test('names $field when it is missing', () {
        final incomplete = {..._valid}..remove(field);

        expect(
          () => FirebaseConfig.parse(jsonEncode(incomplete)),
          throwsA(
            isA<ConfigException>().having(
              (e) => e.message,
              'message',
              contains(field),
            ),
          ),
        );
      });
    }

    test('names an empty field', () {
      final blank = {..._valid, 'uid': '  '};

      expect(
        () => FirebaseConfig.parse(jsonEncode(blank)),
        throwsA(
          isA<ConfigException>().having(
            (e) => e.message,
            'message',
            contains('uid'),
          ),
        ),
      );
    });

    test('names an unfilled placeholder', () {
      final unfilled = {..._valid, 'apiKey': 'PASTE_WEB_API_KEY_HERE'};

      expect(
        () => FirebaseConfig.parse(jsonEncode(unfilled)),
        throwsA(
          isA<ConfigException>().having(
            (e) => e.message,
            'message',
            contains('placeholder for: apiKey'),
          ),
        ),
      );
    });

    test('rejects unparsable JSON', () {
      expect(
        () => FirebaseConfig.parse('{not json'),
        throwsA(isA<ConfigException>()),
      );
    });

    test('rejects a non-object document', () {
      expect(
        () => FirebaseConfig.parse('["a list"]'),
        throwsA(isA<ConfigException>()),
      );
    });

    test('has a readable toString on the exception', () {
      expect(ConfigException('boom').toString(), contains('boom'));
    });
  });

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

    test('refuses a Google account that is not the configured uid', () async {
      // End of the chain the phone actually walks: a mis-tapped account in the
      // picker must fail here rather than storing a session that the security
      // rules then deny on every read and write.
      final store = InMemoryCredentialStore();
      final mock = http_testing.MockClient(
        (request) async => http.Response(
          jsonEncode({
            'idToken': 'id',
            'refreshToken': 'refresh',
            'expiresIn': '3600',
            'localId': 'a-different-persons-uid',
          }),
          200,
        ),
      );

      await expectLater(
        firebaseClientFor(
          config: FirebaseConfig.parse(jsonEncode(_valid)),
          store: store,
          googleIdToken: () async => 'token-for-the-wrong-account',
          httpClient: mock,
        ),
        throwsA(isA<FirebaseAuthError>()),
      );
      expect(await store.load(), isNull);
    });

    test('falls back to the password when Google returns null', () async {
      // Desktop and headless: the provider is wired but nobody is signed in
      // with Google, so the machine credential has to still work.
      final sentTo = <String>[];
      final mock = http_testing.MockClient((request) async {
        sentTo.add(request.url.path);
        return http.Response(
          jsonEncode({
            'idToken': 'id',
            'refreshToken': 'refresh',
            'expiresIn': '3600',
          }),
          200,
        );
      });

      final client = await firebaseClientFor(
        config: FirebaseConfig.parse(jsonEncode(_valid)),
        store: InMemoryCredentialStore(),
        password: 'hunter2',
        googleIdToken: () async => null,
        httpClient: mock,
      );

      expect(sentTo.single, contains('signInWithPassword'));
      client.close();
    });

    test('refuses to build when Google returns null and no password', () async {
      await expectLater(
        firebaseClientFor(
          config: FirebaseConfig.parse(jsonEncode(_valid)),
          store: InMemoryCredentialStore(),
          googleIdToken: () async => null,
        ),
        throwsA(isA<ConfigException>()),
      );
    });

    test('reuses a stored session without a password', () async {
      final store = InMemoryCredentialStore();
      await store.save(
        FirebaseCredentials(
          idToken: 'id',
          refreshToken: 'refresh',
          expiresAt: DateTime.now().add(const Duration(hours: 1)),
        ),
      );

      final client = await firebaseClientFor(
        config: FirebaseConfig.parse(jsonEncode(_valid)),
        store: store,
      );

      expect(client, isA<FirebaseRestClient>());
      client.close();
    });

    test(
      'mirrorStoreFor makes Firebase primary and GitHub the mirror',
      () async {
        // Which backend is authoritative is the one thing a rollback depends on.
        final store = InMemoryCredentialStore();
        await store.save(
          FirebaseCredentials(
            idToken: 'id',
            refreshToken: 'refresh',
            expiresAt: DateTime.now().add(const Duration(hours: 1)),
          ),
        );
        final github = _StubRemote();

        final mirror = await mirrorStoreFor(
          config: FirebaseConfig.parse(jsonEncode(_valid)),
          store: store,
          githubClient: github,
        );

        expect(mirror.primary, isA<FirebaseRestClient>());
        expect(mirror.mirror, same(github));
        mirror.close();
      },
    );
  });
}
