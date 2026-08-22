/// Tests for the public/private split of the Firebase settings.
///
/// Every repo in this fleet is public, so which half a value lands in is a
/// disclosure decision, not a style choice. These tests pin that split.
library;

import 'package:crdt_sync/crdt_sync.dart';
import 'package:test/test.dart';

const _project = FirebaseProject(
  apiKey: 'AIzaSyExample',
  databaseUrl: 'https://x-rtdb.europe-west1.firebasedatabase.app',
);

void main() {
  group('FirebaseProject', () {
    test('parses the project half of a firebase.json', () {
      final project = FirebaseProject.fromJson(const {
        'apiKey': 'AIzaSyExample',
        'databaseUrl': 'https://x-rtdb.europe-west1.firebasedatabase.app',
        'projectId': 'ignored',
        'uid': 'ignored',
        'email': 'ignored',
      });

      expect(project.apiKey, 'AIzaSyExample');
      expect(project.databaseUrl, endsWith('firebasedatabase.app'));
    });

    test('builds a usable config from a per-device email', () {
      final config = _project.configFor('someone@example.com');

      expect(config.apiKey, _project.apiKey);
      expect(config.databaseUrl, _project.databaseUrl);
      expect(config.email, 'someone@example.com');
    });

    test('carries no uid, because the rules check it server-side', () {
      // A client-side copy of the uid adds a way to be wrong without adding
      // any protection: the database refuses a wrong account regardless.
      expect(_project.configFor('a@b.c').uid, isEmpty);
    });
  });

  group('FirebaseAccount', () {
    test('round-trips through the keystore blob', () {
      const account = FirebaseAccount(email: 'a@b.c', password: 'hunter2');

      final parsed = FirebaseAccount.tryParse(account.toJsonString());

      expect(parsed, isNotNull);
      expect(parsed!.email, 'a@b.c');
      expect(parsed.password, 'hunter2');
    });

    test('is keyed apart from the token and the refresh credentials', () {
      // All three coexist for the whole mirrored cutover.
      expect(kFirebaseAccountKey, isNot('sync.token'));
      expect(kFirebaseAccountKey, isNot(SecureCredentialStore.defaultKey));
    });

    for (final (name, raw) in <(String, String?)>[
      ('null', null),
      ('empty', ''),
      ('corrupt JSON', '{oops'),
      ('a list', '[1,2]'),
      ('a missing password', '{"email":"a@b.c"}'),
      ('a non-string email', '{"email":1,"password":"p"}'),
      ('an empty email', '{"email":"","password":"p"}'),
    ]) {
      test('treats $name as not configured', () {
        expect(FirebaseAccount.tryParse(raw), isNull);
      });
    }

    test('accepts an empty password, which Google sign-in writes', () {
      // Regression: this used to return null, so a device that signed in with
      // Google -- or adopted a seeded session -- wrote an account marker it
      // could never read back. Every later launch reported "not configured"
      // and fell through to the mirror, while a perfectly good refresh token
      // sat unused in the keystore beside it.
      final parsed = FirebaseAccount.tryParse(
        const FirebaseAccount(email: 'a@b.c', password: '').toJsonString(),
      );

      expect(parsed, isNotNull);
      expect(parsed!.email, 'a@b.c');
      expect(parsed.password, isEmpty);
    });
  });
}
