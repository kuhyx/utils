import 'dart:convert';
import 'dart:io';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart' as http_testing;
import 'package:test/test.dart';

const _databaseUrl = 'https://example-default-rtdb.firebasedatabase.app';

FirebaseTokenProvider _auth() => FirebaseTokenProvider(
  apiKey: 'fake-api-key',
  store: InMemoryCredentialStore(
    FirebaseCredentials(
      idToken: 'id-token',
      refreshToken: 'refresh-token',
      expiresAt: DateTime.utc(2099),
    ),
  ),
  httpClient: http_testing.MockClient(
    (_) async => throw StateError('auth must not be contacted'),
  ),
);

/// Client over an in-memory transport that records every request path.
(FirebaseRestClient, List<http.Request>) _client(String? namespace) {
  final requests = <http.Request>[];
  final mock = http_testing.MockClient((request) async {
    requests.add(request);
    return http.Response(jsonEncode(request.method == 'GET' ? null : 'x'), 200);
  });
  final client = namespace == null
      ? FirebaseRestClient(
          databaseUrl: _databaseUrl,
          auth: _auth(),
          httpClient: mock,
        )
      : FirebaseRestClient(
          databaseUrl: _databaseUrl,
          auth: _auth(),
          httpClient: mock,
          namespace: namespace,
        );
  return (client, requests);
}

void main() {
  group('compile-time default', () {
    test('is empty when SYNC_NAMESPACE is not defined', () {
      expect(syncNamespace, isEmpty);
    });

    test('empty namespace leaves paths byte-for-byte unchanged', () async {
      final (client, requests) = _client(null);
      await client.getFileText('devices/pc/log.json');
      expect(requests.single.url.path, '/devices/pc/log~2Ejson.json');
    });
  });

  group('prefixing', () {
    test('every operation lands under the namespace', () async {
      final (client, requests) = _client('sandbox/slot3');
      await client.getFileText('devices/pc/log.json');
      await client.putFileText('devices/pc/log.json', 't', message: 'm');
      await client.listDirectory('devices');
      await client.getStringMap('revs');
      await client.patchValues('revs', {'a': 'b'});
      await client.deleteFile('devices/pc/log.json');
      await client.canAccessRemote();
      expect(requests.map((r) => r.url.path), [
        '/sandbox/slot3/devices/pc/log~2Ejson.json',
        '/sandbox/slot3/devices/pc/log~2Ejson.json',
        '/sandbox/slot3/devices.json',
        '/sandbox/slot3/revs.json',
        '/sandbox/slot3/revs.json',
        '/sandbox/slot3/devices/pc/log~2Ejson.json',
        '/sandbox/slot3.json',
      ]);
    });

    test('an explicitly empty namespace is the unprefixed path', () async {
      final (client, requests) = _client('');
      await client.getStringMap('revs');
      expect(requests.single.url.path, '/revs.json');
    });
  });

  group('validation (fail closed)', () {
    const bad = [
      'sandbox',
      'sandbox/',
      'sandbox/Slot3',
      'sandbox/slot 3',
      'sandbox/slot3/',
      'sandbox/a/b',
      '/sandbox/slot3',
      'prod/slot3',
      'sandbox/slot3\n',
      'Sandbox/slot3',
      'sandbox/slot.3',
      'sandbox/..',
    ];

    for (final value in bad) {
      test('rejects ${jsonEncode(value)}', () {
        expect(
          () => checkSyncNamespace(value),
          throwsA(isA<ConfigException>()),
        );
        expect(
          () => FirebaseRestClient(
            databaseUrl: _databaseUrl,
            auth: _auth(),
            namespace: value,
          ),
          throwsA(isA<ConfigException>()),
        );
      });
    }

    test('the message names the define and the required shape', () {
      expect(
        () => checkSyncNamespace('typo'),
        throwsA(
          isA<ConfigException>().having(
            (e) => e.message,
            'message',
            allOf(
              contains('SYNC_NAMESPACE'),
              contains(r'^sandbox/[a-z0-9_-]+$'),
            ),
          ),
        ),
      );
    });

    test('accepts the allowed alphabet', () {
      expect(() => checkSyncNamespace('sandbox/slot3'), returnsNormally);
      expect(() => checkSyncNamespace('sandbox/a_b-c9'), returnsNormally);
      expect(() => checkSyncNamespace(''), returnsNormally);
    });

    test(
      'a bad compile-time define stops firebaseClientFor at startup',
      () async {
        // The define is compile-time, so only a fresh process can set it.
        final result = await Process.run(Platform.resolvedExecutable, [
          '-DSYNC_NAMESPACE=sandbox/Typo',
          'run',
          'tool/namespace_probe.dart',
        ]);
        expect(result.exitCode, isNot(0));
        expect(
          result.stderr,
          contains('SYNC_NAMESPACE "sandbox/Typo" is invalid'),
        );
      },
    );

    test('a good compile-time define reaches the request path', () async {
      final result = await Process.run(Platform.resolvedExecutable, [
        '-DSYNC_NAMESPACE=sandbox/slot3',
        'run',
        'tool/namespace_probe.dart',
      ]);
      expect(result.stderr, isEmpty);
      expect(result.stdout, '/sandbox/slot3/devices.json\n');
    });
  });
}
