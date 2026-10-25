// A real ClientException carries the request URL, and its toString prints
// it: `uri=https://<db>/<path>.json?auth=<ID token>` for RTDB, `?key=<API
// key>` for auth. Error messages end up in UIs and logs, so neither may
// ever contain the URL's query.
import 'package:crdt_sync/crdt_sync.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart' as http_testing;
import 'package:test/test.dart';

/// Fails every request the way IOClient does: message plus request URL.
http.Client _offline() => http_testing.MockClient(
  (request) async =>
      throw http.ClientException('Failed host lookup', request.url),
);

FirebaseRestClient _client() => FirebaseRestClient(
  databaseUrl: 'https://db.example',
  auth: FirebaseTokenProvider(
    apiKey: 'fake-api-key',
    store: InMemoryCredentialStore(
      FirebaseCredentials(
        idToken: 'SECRET-ID-TOKEN',
        refreshToken: 'refresh-token',
        expiresAt: DateTime.utc(2099),
      ),
    ),
    httpClient: _offline(),
  ),
  httpClient: _offline(),
);

Matcher _redacted<T>(String secret) => throwsA(
  isA<T>()
      .having((e) => '$e', 'text', contains('Failed host lookup'))
      .having((e) => '$e', 'text', isNot(contains(secret))),
);

void main() {
  const token = 'SECRET-ID-TOKEN';
  final ops = <String, Future<void> Function(FirebaseRestClient)>{
    'getFileText': (c) => c.getFileText('ns/a.json'),
    'listDirectory': (c) => c.listDirectory('ns'),
    'getStringMap': (c) => c.getStringMap('ns/revs'),
    'putFileText': (c) => c.putFileText('ns/a.json', 'x', message: 'm'),
    'patchValues': (c) => c.patchValues('ns/revs', {'a': '1'}),
    'deleteFile': (c) => c.deleteFile('ns/a.json'),
  };
  for (final MapEntry(key: name, value: op) in ops.entries) {
    test('$name: a network error never shows the ID token', () {
      expect(op(_client()), _redacted<FirebaseSyncError>(token));
    });
  }

  test('auth: a network error never shows the API key', () {
    final provider = FirebaseTokenProvider(
      apiKey: 'SECRET-API-KEY',
      store: InMemoryCredentialStore(),
      httpClient: _offline(),
    );
    expect(
      provider.signIn(email: 'a@b.c', password: 'x'),
      _redacted<FirebaseAuthError>('SECRET-API-KEY'),
    );
  });
}
