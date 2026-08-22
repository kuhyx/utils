import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart' as http_testing;
import 'package:test/test.dart';

const _databaseUrl =
    'https://example-default-rtdb.europe-west1.firebasedatabase.app';

http.Response _json(int statusCode, Object? body) =>
    http.Response(jsonEncode(body), statusCode);

/// A provider holding a long-lived token, so client tests never hit the auth
/// endpoints -- an HTTP call from the token provider would fail loudly here.
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

/// Records every request the client makes, so tests can assert on the URL
/// (which carries the key escaping and the shallow flag) as well as the
/// decoded result.
late List<http.Request> requests;

FirebaseRestClient _client(Object response, {FirebaseTokenProvider? auth}) {
  requests = [];
  final mock = http_testing.MockClient((request) async {
    requests.add(request);
    if (response is http.ClientException) throw response;
    return response as http.Response;
  });
  return FirebaseRestClient(
    databaseUrl: _databaseUrl,
    auth: auth ?? _auth(),
    httpClient: mock,
  );
}

void main() {
  group('putFileText', () {
    test('writes the text as a JSON string leaf', () async {
      final client = _client(_json(200, '{"a":1}'));
      await client.putFileText(
        'ns/devices/pc/log.json',
        '{"a":1}',
        message: 'ignored by rtdb',
      );
      expect(requests.single.method, 'PUT');
      expect(requests.single.body, jsonEncode('{"a":1}'));
      expect(requests.single.url.path, '/ns/devices/pc/log~2Ejson.json');
    });

    test('raises on a non-2xx response', () async {
      final client = _client(_json(400, {'error': 'bad'}));
      expect(
        () => client.putFileText('ns/devices/pc/log.json', '{}', message: 'm'),
        throwsA(isA<FirebaseSyncError>()),
      );
    });

    test('turns a network failure into FirebaseSyncError', () async {
      final client = _client(http.ClientException('offline'));
      expect(
        () => client.putFileText('ns/devices/pc/log.json', '{}', message: 'm'),
        throwsA(isA<FirebaseSyncError>()),
      );
    });
  });

  group('patchValues', () {
    test('PATCHes rather than PUTs, so sibling keys survive', () async {
      // A PUT on the shared revs map would wipe every other device's entry,
      // after which those devices would look permanently unchanged and never
      // be fetched again.
      final client = _client(_json(200, {'pc': 'abc'}));
      await client.patchValues('ns/revs', {'pc': 'abc'});
      expect(requests.single.method, 'PATCH');
      expect(requests.single.body, jsonEncode({'pc': 'abc'}));
    });

    test('raises on a non-2xx response', () async {
      final client = _client(_json(500, {'error': 'boom'}));
      expect(
        () => client.patchValues('ns/revs', {'pc': 'abc'}),
        throwsA(isA<FirebaseSyncError>()),
      );
    });

    test('turns a network failure into FirebaseSyncError', () async {
      final client = _client(http.ClientException('offline'));
      expect(
        () => client.patchValues('ns/revs', {'pc': 'abc'}),
        throwsA(isA<FirebaseSyncError>()),
      );
    });
  });

  group('getStringMap', () {
    test('returns the map with keys decoded', () async {
      final client = _client(_json(200, {'pc': 'sha-1', 'phone': 'sha-2'}));
      expect(await client.getStringMap('ns/revs'), {
        'pc': 'sha-1',
        'phone': 'sha-2',
      });
    });

    test('degrades to empty when absent', () async {
      final client = _client(_json(200, null));
      expect(await client.getStringMap('ns/revs'), isEmpty);
    });

    test('skips non-string entries rather than failing the sync', () async {
      // The revs node is an optimisation; a corrupt one must degrade into
      // "fetch everything", never into a failed tick.
      final client = _client(_json(200, {'pc': 'sha-1', 'phone': 42}));
      expect(await client.getStringMap('ns/revs'), {'pc': 'sha-1'});
    });

    test('raises on a non-2xx response', () async {
      final client = _client(_json(500, {'error': 'boom'}));
      expect(
        () => client.getStringMap('ns/revs'),
        throwsA(isA<FirebaseSyncError>()),
      );
    });
  });

  group('deleteFile', () {
    test('sends a DELETE to the escaped path', () async {
      final client = _client(_json(200, null));
      await client.deleteFile('ns/devices/pc/log.json');
      expect(requests.single.method, 'DELETE');
      expect(requests.single.url.path, '/ns/devices/pc/log~2Ejson.json');
    });

    test('raises on a non-2xx response', () async {
      final client = _client(_json(500, {'error': 'boom'}));
      expect(
        () => client.deleteFile('ns/devices/pc/log.json'),
        throwsA(isA<FirebaseSyncError>()),
      );
    });

    test('turns a network failure into FirebaseSyncError', () async {
      final client = _client(http.ClientException('offline'));
      expect(
        () => client.deleteFile('ns/devices/pc/log.json'),
        throwsA(isA<FirebaseSyncError>()),
      );
    });
  });

  group('canAccessRemote', () {
    test('is true when the database root reads', () async {
      expect(await _client(_json(200, {'ns': true})).canAccessRemote(), isTrue);
    });

    test('is false when the rules reject the token', () async {
      expect(
        await _client(_json(401, {'error': 'denied'})).canAccessRemote(),
        isFalse,
      );
    });

    test('is false on a network error', () async {
      expect(
        await _client(http.ClientException('offline')).canAccessRemote(),
        isFalse,
      );
    });

    test('is false when no session is stored, rather than throwing', () async {
      // "cannot get a token" is exactly "cannot access the remote", and a
      // settings screen's Test-connection button must not blow up.
      final client = _client(
        _json(200, {}),
        auth: FirebaseTokenProvider(
          apiKey: 'k',
          store: InMemoryCredentialStore(),
          httpClient: http_testing.MockClient((_) async => _json(200, {})),
        ),
      );
      expect(await client.canAccessRemote(), isFalse);
    });
  });

  group('RemoteStore contract', () {
    test('FirebaseRestClient is a RemoteStore', () {
      expect(_client(_json(200, null)), isA<RemoteStore>());
    });

    test('DatabaseNotFoundError is catchable as either error type', () {
      final error = DatabaseNotFoundError('gone');
      expect(error, isA<FirebaseSyncError>());
      expect(error, isA<RemoteNotFoundError>());
      expect(error, isA<RemoteSyncError>());
    });

    test('a trailing slash on the database URL is tolerated', () async {
      final client = FirebaseRestClient(
        databaseUrl: '$_databaseUrl/',
        auth: _auth(),
        httpClient: http_testing.MockClient((request) async {
          requests.add(request);
          return _json(200, 'ok');
        }),
      );
      requests = [];
      await client.getFileText('ns/x.json');
      expect(requests.single.url.toString(), startsWith('$_databaseUrl/ns/'));
    });

    test('close releases the HTTP client', () {
      expect(_client(_json(200, null)).close, returnsNormally);
    });
  });
}
