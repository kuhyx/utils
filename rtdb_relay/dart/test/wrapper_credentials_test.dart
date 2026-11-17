import 'dart:convert';

import 'package:crdt_sync/crdt_sync.dart' show InMemoryCredentialStore;
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:rtdb_relay/src/auth.dart';
import 'package:rtdb_relay/src/wrapper_credentials.dart';

String _jwt(Map<String, Object> payload) {
  final body = base64Url.encode(utf8.encode(jsonEncode(payload)));
  return 'h.${body.replaceAll('=', '')}.s';
}

Map<String, Object> _creds(String token) => {
  'id_token': token,
  'refresh_token': 'r',
  'expires_at': '2099-01-01T00:00:00.000Z',
};

void main() {
  final base = Uri.parse('http://127.0.0.1:8778/app/');

  test('uid from the id token', () {
    expect(uidOfIdToken(_jwt({'user_id': 'u'})), 'u');
    expect(uidOfIdToken(_jwt({'sub': 's'})), 's');
    expect(uidOfIdToken(_jwt({'sub': 1})), isNull);
    expect(uidOfIdToken('a.b'), isNull);
    expect(uidOfIdToken('a.!!!.c'), isNull);
    expect(uidOfIdToken('h.${base64Url.encode(utf8.encode('[1]'))}.s'), isNull);
  });

  Future<bool> adopt(http.Response Function(http.Request) answer) async {
    final store = InMemoryCredentialStore();
    final ok = await adoptWrapperCredentials(
      base: base,
      client: MockClient((r) async {
        expect(r.url.path, '/app/sync-credentials');
        return answer(r);
      }),
      store: store,
      expectedUid: 'u',
    );
    expect(await store.load() != null, ok);
    return ok;
  }

  test('adopts the right account only', () async {
    expect(
      await adopt(
        (_) => http.Response(jsonEncode(_creds(_jwt({'user_id': 'u'}))), 200),
      ),
      isTrue,
    );
    expect(
      await adopt(
        (_) => http.Response(jsonEncode(_creds(_jwt({'user_id': 'x'}))), 200),
      ),
      isFalse,
    );
    expect(await adopt((_) => http.Response('', 404)), isFalse);
    expect(await adopt((_) => http.Response('[1]', 200)), isFalse);
    expect(
      await adopt((_) => http.Response(jsonEncode({'id_token': 'x'}), 200)),
      isFalse,
    );
    expect(
      await adopt((_) => throw http.ClientException('no wrapper')),
      isFalse,
    );
  });

  test('auth: the desktop adopts on the first session probe', () async {
    final token = _jwt({'user_id': 'u'});
    final store = InMemoryCredentialStore();
    final client = MockClient(
      (_) async => http.Response(jsonEncode(_creds(token)), 200),
    );
    final auth = RelayAuth(
      config: const RelayFirebaseConfig(
        apiKey: 'k',
        databaseUrl: 'https://db',
        syncUid: 'u',
        serverClientId: '',
      ),
      googleToken: ({required serverClientId}) async => null,
      store: store,
      httpClient: client,
      adopt: () => adoptWrapperCredentials(
        base: base,
        client: client,
        store: store,
        expectedUid: 'u',
      ),
    );
    expect(await auth.hasSession(), isTrue);
  });
}
