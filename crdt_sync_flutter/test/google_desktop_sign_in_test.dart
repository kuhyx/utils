import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:crdt_sync_flutter/crdt_sync_flutter.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

/// Binds a real loopback server on an OS-chosen port.
///
/// A real socket rather than a fake: `dart:io` works under `flutter test`
/// (it is the platform *channels* that do not), and the redirect handling is
/// exactly the part worth exercising against a real HTTP round trip.
Future<HttpServer> _bind() => HttpServer.bind(InternetAddress.loopbackIPv4, 0);

/// Drives the browser half: reads the port out of the auth URL and issues the
/// redirect Google would have issued.
BrowserLauncher _respondingLauncher(
  Map<String, String> Function(String state) params,
) => (url) async {
  final port = Uri.parse(url.queryParameters['redirect_uri']!).port;
  final state = url.queryParameters['state']!;
  unawaited(
    http.get(
      Uri.parse('http://127.0.0.1:$port/').replace(
        queryParameters: params(state),
      ),
    ),
  );
  return true;
};

void main() {
  test('exchanges the code for an id token', () async {
    late Map<String, String> sentBody;
    final client = MockClient((request) async {
      sentBody = Uri.splitQueryString(request.body);
      return http.Response('{"id_token":"the-token"}', 200);
    });

    final token = await googleDesktopIdToken(
      clientId: 'desktop-cid',
      binder: _bind,
      launcher: _respondingLauncher(
        (state) => {'code': 'auth-code', 'state': state},
      ),
      httpClient: client,
      pkce: PkcePair.fromVerifier('v', 'ignored-state'),
    );

    expect(token, 'the-token');
    expect(sentBody['code'], 'auth-code');
    expect(sentBody['code_verifier'], 'v');
  });

  test('returns null when the user denies consent', () async {
    final token = await googleDesktopIdToken(
      clientId: 'cid',
      binder: _bind,
      launcher: _respondingLauncher(
        (state) => {'error': 'access_denied', 'state': state},
      ),
      httpClient: MockClient((_) async => http.Response('{}', 200)),
    );
    expect(token, isNull);
  });

  test('returns null when a forged redirect carries the wrong state', () async {
    final token = await googleDesktopIdToken(
      clientId: 'cid',
      binder: _bind,
      launcher: _respondingLauncher(
        (_) => {'code': 'c', 'state': 'not-the-state'},
      ),
      httpClient: MockClient((_) async => http.Response('{}', 200)),
    );
    expect(token, isNull);
  });

  test('returns null, and does not wait, when no browser opens', () async {
    var posted = false;
    final token = await googleDesktopIdToken(
      clientId: 'cid',
      binder: _bind,
      launcher: (_) async => false,
      httpClient: MockClient((_) async {
        posted = true;
        return http.Response('{}', 200);
      }),
      // Would hang for the full timeout if the launcher result were ignored.
      timeout: const Duration(seconds: 30),
    );
    expect(token, isNull);
    expect(posted, isFalse);
  });

  test('returns null when the token endpoint rejects the code', () async {
    final token = await googleDesktopIdToken(
      clientId: 'cid',
      binder: _bind,
      launcher: _respondingLauncher(
        (state) => {'code': 'c', 'state': state},
      ),
      httpClient: MockClient(
        (_) async => http.Response('{"error":"invalid_grant"}', 400),
      ),
    );
    expect(token, isNull);
  });

  test('gives up when the user never finishes', () async {
    final token = await googleDesktopIdToken(
      clientId: 'cid',
      binder: _bind,
      launcher: (_) async => true,
      httpClient: MockClient((_) async => http.Response('{}', 200)),
      timeout: const Duration(milliseconds: 50),
    );
    expect(token, isNull);
  });

  test('rejects an empty client id without binding a socket', () async {
    var bound = false;
    final token = await googleDesktopIdToken(
      clientId: '',
      binder: () async {
        bound = true;
        return _bind();
      },
      launcher: (_) async => true,
    );
    expect(token, isNull);
    expect(bound, isFalse);
  });

  test('serves a readable page after a successful redirect', () async {
    final pageBody = Completer<String>();

    await googleDesktopIdToken(
      clientId: 'cid',
      binder: _bind,
      // Deliberately NOT awaited: googleDesktopIdToken awaits the launcher
      // before it starts listening, so a launcher that blocks on the response
      // deadlocks against a server that has not begun serving.
      launcher: (url) async {
        final port = Uri.parse(url.queryParameters['redirect_uri']!).port;
        final state = url.queryParameters['state']!;
        unawaited(
          http
              .get(Uri.parse('http://127.0.0.1:$port/?code=c&state=$state'))
              .then((response) => pageBody.complete(response.body)),
        );
        return true;
      },
      httpClient: MockClient(
        (_) async => http.Response('{"id_token":"t"}', 200),
      ),
    );

    expect(await pageBody.future, contains('Signed in'));
  });

  test('binds a real loopback socket by default', () async {
    // Covers the production binder rather than only the injected one: a
    // default that cannot bind would fail on the user's desktop and nowhere
    // in this suite.
    var launched = false;
    final token = await googleDesktopIdToken(
      clientId: 'cid',
      launcher: (url) async {
        launched = true;
        expect(
          Uri.parse(url.queryParameters['redirect_uri']!).port,
          isPositive,
        );
        return false;
      },
      httpClient: MockClient((_) async => http.Response('{}', 200)),
    );
    expect(token, isNull);
    expect(launched, isTrue);
  });

  test('creates and closes its own http client when none is passed', () async {
    // The httpClient == null branch: no request is ever made (the launcher
    // reports no browser), but the client is still constructed and closed.
    final token = await googleDesktopIdToken(
      clientId: 'cid',
      binder: _bind,
      launcher: (_) async => false,
    );
    expect(token, isNull);
  });

  test('closes the server it opened', () async {
    late int boundPort;
    await googleDesktopIdToken(
      clientId: 'cid',
      binder: () async {
        final server = await _bind();
        // Captured while still bound: `.port` throws once closed, which is
        // exactly the invariant this test exists to confirm.
        boundPort = server.port;
        return server;
      },
      launcher: (_) async => true,
      httpClient: MockClient((_) async => http.Response('{}', 200)),
      timeout: const Duration(milliseconds: 50),
    );
    // Rebinding the same port only succeeds if the first was released.
    final rebound = await HttpServer.bind(
      InternetAddress.loopbackIPv4,
      boundPort,
    );
    await rebound.close(force: true);
  });
}
