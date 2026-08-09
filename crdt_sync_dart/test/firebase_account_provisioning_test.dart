import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart' as http_testing;
import 'package:test/test.dart';

final _base = Uri.parse('http://localhost:8730');

void main() {
  group('accountFromWrapper', () {
    test('parses the account the wrapper serves', () async {
      final client = http_testing.MockClient(
        (request) async => http.Response(
          jsonEncode({'email': 'a@b.c', 'password': 'pw'}),
          200,
        ),
      );

      final account = await accountFromWrapper(_base, client: client);

      expect(account?.email, 'a@b.c');
      expect(account?.password, 'pw');
    });

    test('requests the shared route path', () async {
      var requested = '';
      final client = http_testing.MockClient((request) async {
        requested = request.url.path;
        return http.Response('{}', 404);
      });

      await accountFromWrapper(_base, client: client);

      expect(requested, kSyncAccountPath);
    });

    test('a missing route is not configured, not an error', () async {
      // The normal case: the route is opt-in, so 404 is what most launches
      // see and it must degrade to "ask the user" rather than throw.
      final client = http_testing.MockClient(
        (request) async => http.Response('', 404),
      );

      expect(await accountFromWrapper(_base, client: client), isNull);
    });

    test('a malformed body yields null rather than throwing', () async {
      final client = http_testing.MockClient(
        (request) async => http.Response('{not json', 200),
      );

      expect(await accountFromWrapper(_base, client: client), isNull);
    });

    test('a body missing the password yields null', () async {
      final client = http_testing.MockClient(
        (request) async => http.Response(jsonEncode({'email': 'a@b.c'}), 200),
      );

      expect(await accountFromWrapper(_base, client: client), isNull);
    });

    test('a wrapper that is not running yields null', () async {
      final client = http_testing.MockClient(
        (request) async => throw http.ClientException('refused'),
      );

      expect(await accountFromWrapper(_base, client: client), isNull);
    });
  });
}
