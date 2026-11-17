import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:rtdb_relay/src/rtdb_client.dart';

import 'support/tutor_layout.dart';

/// Records every request the client sends.
class _Spy {
  final seen = <http.Request>[];

  RtdbClient client({String? namespace}) => RtdbClient(
    layout: tutorLayout,
    databaseUrl: 'https://db/',
    idToken: () async => 'tok',
    namespace: namespace,
    httpClient: MockClient((req) async {
      seen.add(req);
      return http.Response('null', 200, headers: {'etag': 'e1'});
    }),
  );
}

void main() {
  test('empty namespace keeps every path byte-identical', () async {
    final spy = _Spy();
    final c = spy.client(namespace: '');
    await c.get('tutor/v1-e2e/a');
    await c.put('/tutor/v1-e2e/b/', 1);
    await c.patch('tutor/v1-e2e/c', {'k': 1});
    await c.delete('tutor/v1-e2e/d');
    await c.getTagged('tutor/v1-e2e/e');
    await c.putIfMatch('tutor/v1-e2e/f', 1, 'e1');
    await c.deleteIfMatch('tutor/v1-e2e/g', 'e1');
    await c.keys('tutor/v1-e2e/h');
    expect(spy.seen.map((r) => r.url.path), [
      '/tutor/v1-e2e/a.json',
      '/tutor/v1-e2e/b.json',
      '/tutor/v1-e2e/c.json',
      '/tutor/v1-e2e/d.json',
      '/tutor/v1-e2e/e.json',
      '/tutor/v1-e2e/f.json',
      '/tutor/v1-e2e/g.json',
      '/tutor/v1-e2e/h.json',
    ]);
  });

  test('a sandbox namespace prefixes every request path', () async {
    final spy = _Spy();
    final c = spy.client(namespace: 'sandbox/slot3');
    await c.get('tutor/v1-e2e/a');
    await c.put('/tutor/v1-e2e/b/', 1);
    await c.patch('tutor/v1-e2e/c', {'k': 1});
    await c.delete('tutor/v1-e2e/d');
    await c.getTagged('tutor/v1-e2e/e');
    await c.putIfMatch('tutor/v1-e2e/f', 1, 'e1');
    await c.deleteIfMatch('tutor/v1-e2e/g', 'e1');
    await c.keys('tutor/v1-e2e/h');
    expect(
      spy.seen.map((r) => r.url.path),
      everyElement(startsWith('/sandbox/slot3/tutor/v1-e2e/')),
    );
    expect(spy.seen, hasLength(8));
  });

  test('uri (used by the SSE stream) is prefixed too', () async {
    final c = _Spy().client(namespace: 'sandbox/slot3');
    expect(
      (await c.uri('tutor/v1-e2e/rev')).path,
      '/sandbox/slot3/tutor/v1-e2e/rev.json',
    );
  });

  test('an invalid namespace fails closed at construction', () {
    for (final bad in [
      'slot3',
      'sandbox/',
      'sandbox/Slot',
      'prod',
      '/x',
      'sandbox/a/b',
      'sandbox/s\n',
    ]) {
      expect(() => _Spy().client(namespace: bad), throwsException, reason: bad);
    }
  });

  test('the compiled define defaults to empty (production paths)', () async {
    final c = _Spy().client();
    expect((await c.uri('a')).path, '/a.json');
  });
}
