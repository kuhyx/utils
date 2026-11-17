import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:rtdb_relay/src/rtdb_client.dart';

import 'support/tutor_layout.dart';

RtdbClient _client(MockClientHandler handler, {String url = 'https://db/'}) =>
    RtdbClient(
      layout: tutorLayout,
      databaseUrl: url,
      idToken: () async => 'tok',
      httpClient: MockClient(handler),
    );

void main() {
  test('uri encodes segments and carries the token and query', () async {
    final c = _client((_) async => http.Response('null', 200));
    final uri = await c.uri(
      '/tutor/v1-e2e/a b/',
      query: keyRangeQuery('m0003'),
    );
    expect(uri.path, '/tutor/v1-e2e/a%20b.json');
    expect(uri.queryParameters['auth'], 'tok');
    expect(uri.queryParameters['orderBy'], r'"$key"');
    expect(uri.queryParameters['startAt'], '"m0003"');
    final noSlash = RtdbClient(
      layout: tutorLayout,
      databaseUrl: 'https://x',
      idToken: () async => 't',
    );
    expect((await noSlash.uri('a')).toString(), startsWith('https://x/a.json'));
    noSlash.close();
  });

  test('get decodes JSON; empty body is null; keys are sorted', () async {
    final c = _client((req) async {
      if (req.url.queryParameters['shallow'] == 'true') {
        return http.Response('{"b":true,"a":true}', 200);
      }
      return http.Response(req.url.path == '/e.json' ? '' : '{"x":1}', 200);
    });
    expect(await c.get('v'), {'x': 1});
    expect(await c.get('e'), isNull);
    expect(await c.keys('v'), ['a', 'b']);
  });

  test('keys of an absent node is empty', () async {
    final c = _client((_) async => http.Response('null', 200));
    expect(await c.keys('v'), isEmpty);
  });

  test('put sends JSON and returns the resolved body', () async {
    late http.Request seen;
    final c = _client((req) async {
      seen = req;
      return http.Response('{"created":123}', 200);
    });
    final out = await c.put('r', {
      'created': {'.sv': 'timestamp'},
    });
    expect(seen.method, 'PUT');
    expect(jsonDecode(seen.body), {
      'created': {'.sv': 'timestamp'},
    });
    expect(out, {'created': 123});
  });

  test('getTagged asks for and returns the ETag', () async {
    final c = _client((req) async {
      expect(req.headers['X-Firebase-ETag'], 'true');
      return http.Response('null', 200, headers: {'etag': 'E1'});
    });
    final t = await c.getTagged('claim');
    expect(t.value, isNull);
    expect(t.etag, 'E1');
    final bare = _client((_) async => http.Response('1', 200));
    expect((await bare.getTagged('x')).etag, '');
  });

  test('putIfMatch: success and 412 lost race', () async {
    var status = 200;
    final c = _client((req) async {
      expect(req.headers['if-match'], 'E1');
      return http.Response('{"by":"other"}', status, headers: {'etag': 'E2'});
    });
    final won = await c.putIfMatch('claim', {'by': 'me'}, 'E1');
    expect(won.ok, isTrue);
    status = 412;
    final lost = await c.putIfMatch('claim', {'by': 'me'}, 'E1');
    expect(lost.ok, isFalse);
    expect(lost.value, {'by': 'other'});
    expect(lost.etag, 'E2');
    final del = await c.deleteIfMatch('claim', 'E1');
    expect(del.ok, isFalse);
  });

  test('patch and delete use their methods', () async {
    final methods = <String>[];
    final c = _client((req) async {
      methods.add(req.method);
      return http.Response('null', 200);
    });
    await c.patch('p', {'a': 1});
    await c.delete('p');
    expect(methods, ['PATCH', 'DELETE']);
  });

  test('HTTP errors classify auth vs transient', () async {
    var status = 401;
    final c = _client((_) async => http.Response('{"error":"x"}', status));
    final e401 = await c
        .get('a')
        .then<RtdbError?>((_) => null, onError: (Object e) => e as RtdbError);
    expect(e401!.isAuth, isTrue);
    expect(e401.isTransient, isFalse);
    expect(e401.toString(), contains('401'));
    status = 503;
    await expectLater(
      c.get('a'),
      throwsA(isA<RtdbError>().having((e) => e.isTransient, 't', isTrue)),
    );
    status = 412;
    await expectLater(c.put('a', 1), throwsA(isA<RtdbError>()));
  });

  test('network failure is a transient RtdbError', () async {
    final c = _client((_) async => throw http.ClientException('down'));
    await expectLater(
      c.get('a'),
      throwsA(
        isA<RtdbError>()
            .having((e) => e.status, 'status', isNull)
            .having((e) => e.isTransient, 't', isTrue),
      ),
    );
  });
}
