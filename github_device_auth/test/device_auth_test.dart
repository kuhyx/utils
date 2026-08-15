import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:github_device_auth/github_device_auth.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

/// Never actually waits: the poll loop's pacing is injected so a test that
/// exercises `slow_down` does not take 15 real seconds.
Future<void> noDelay(Duration _) async {}

GitHubDeviceAuth authWith(
  MockClient client, {
  String scope = 'repo',
}) => GitHubDeviceAuth(
  clientId: 'cid',
  scope: scope,
  httpClient: client,
  delay: noDelay,
);

void main() {
  group('DeviceCodeResponse.fromJson', () {
    test('reads every field', () {
      final r = DeviceCodeResponse.fromJson(const {
        'device_code': 'dc',
        'user_code': 'UC-1',
        'verification_uri': 'https://github.com/login/device',
        'interval': 7,
        'expires_in': 100,
      });
      expect(r.deviceCode, 'dc');
      expect(r.userCode, 'UC-1');
      expect(r.verificationUri, 'https://github.com/login/device');
      expect(r.interval, 7);
      expect(r.expiresIn, 100);
    });

    test('defaults interval and expiry when GitHub omits them', () {
      final r = DeviceCodeResponse.fromJson(const {
        'device_code': 'dc',
        'user_code': 'UC',
        'verification_uri': 'u',
      });
      expect(r.interval, 5);
      expect(r.expiresIn, 900);
    });
  });

  test('DeviceAuthException stringifies code and message', () {
    expect(
      DeviceAuthException('access_denied', 'nope').toString(),
      'DeviceAuthException(access_denied): nope',
    );
  });

  group('requestDeviceCode', () {
    test('posts the client id and scope, and parses the response', () async {
      late http.Request seen;
      final auth = authWith(
        MockClient((req) async {
          seen = req;
          return http.Response(
            jsonEncode({
              'device_code': 'dc',
              'user_code': 'UC',
              'verification_uri': 'u',
            }),
            200,
          );
        }),
        scope: 'repo,gist',
      );

      final device = await auth.requestDeviceCode();

      expect(seen.url.toString(), 'https://github.com/login/device/code');
      expect(seen.bodyFields['client_id'], 'cid');
      expect(seen.bodyFields['scope'], 'repo,gist');
      expect(device.userCode, 'UC');
    });

    test('defaults to GitHub s own endpoints', () {
      final auth = GitHubDeviceAuth(clientId: 'cid')..close();
      expect(auth.deviceCodeUrl, githubDeviceCodeUrl);
      expect(auth.tokenUrl, githubTokenUrl);
    });

    test('honours an overridden endpoint', () async {
      // diet-guard's desktop web build routes both endpoints through a local
      // proxy, because GitHub's device-flow endpoints send no CORS headers
      // and a page cannot call them at all.
      late Uri seen;
      final auth = GitHubDeviceAuth(
        clientId: 'cid',
        deviceCodeUrl: 'http://127.0.0.1:9/gh/auth/device/start',
        httpClient: MockClient((req) async {
          seen = req.url;
          return http.Response(
            jsonEncode({
              'device_code': 'dc',
              'user_code': 'UC',
              'verification_uri': 'u',
            }),
            200,
          );
        }),
        delay: noDelay,
      );

      await auth.requestDeviceCode();

      expect(seen.toString(), 'http://127.0.0.1:9/gh/auth/device/start');
    });

    test('throws with the status code on a non-200', () async {
      final auth = authWith(MockClient((_) async => http.Response('bad', 503)));
      await expectLater(
        auth.requestDeviceCode(),
        throwsA(
          isA<DeviceAuthException>()
              .having((e) => e.code, 'code', 'http_503')
              .having((e) => e.message, 'message', 'bad'),
        ),
      );
    });
  });

  group('pollForToken', () {
    const device = DeviceCodeResponse(
      deviceCode: 'dc',
      userCode: 'UC',
      verificationUri: 'u',
      interval: 1,
      expiresIn: 60,
    );

    test('returns the token once the user authorizes', () async {
      var calls = 0;
      final auth = authWith(
        MockClient((_) async {
          calls += 1;
          // First poll pending, second succeeds -- the normal path.
          return http.Response(
            calls == 1
                ? jsonEncode({'error': 'authorization_pending'})
                : jsonEncode({'access_token': 'tok'}),
            200,
          );
        }),
      );
      expect(await auth.pollForToken(device), 'tok');
      expect(calls, 2);
    });

    test('obeys slow_down by taking GitHub s new interval', () async {
      var calls = 0;
      final auth = authWith(
        MockClient((_) async {
          calls += 1;
          return http.Response(
            calls == 1
                ? jsonEncode({'error': 'slow_down', 'interval': 30})
                : jsonEncode({'access_token': 'tok'}),
            200,
          );
        }),
      );
      expect(await auth.pollForToken(device), 'tok');
    });

    test('slow_down without an interval still backs off', () async {
      var calls = 0;
      final auth = authWith(
        MockClient((_) async {
          calls += 1;
          return http.Response(
            calls == 1
                ? jsonEncode({'error': 'slow_down'})
                : jsonEncode({'access_token': 'tok'}),
            200,
          );
        }),
      );
      expect(await auth.pollForToken(device), 'tok');
    });

    test('throws on a terminal error', () async {
      final auth = authWith(
        MockClient(
          (_) async => http.Response(
            jsonEncode({
              'error': 'access_denied',
              'error_description': 'user said no',
            }),
            200,
          ),
        ),
      );
      await expectLater(
        auth.pollForToken(device),
        throwsA(
          isA<DeviceAuthException>()
              .having((e) => e.code, 'code', 'access_denied')
              .having((e) => e.message, 'message', 'user said no'),
        ),
      );
    });

    test('falls back to the code when no description is given', () async {
      final auth = authWith(
        MockClient(
          (_) async => http.Response(jsonEncode({'error': 'expired'}), 200),
        ),
      );
      await expectLater(
        auth.pollForToken(device),
        throwsA(
          isA<DeviceAuthException>().having((e) => e.message, 'msg', 'expired'),
        ),
      );
    });

    test('throws on a response with neither a token nor an error', () async {
      final auth = authWith(
        MockClient((_) async => http.Response(jsonEncode({'x': 1}), 200)),
      );
      await expectLater(
        auth.pollForToken(device),
        throwsA(
          isA<DeviceAuthException>().having((e) => e.code, 'code', 'unknown'),
        ),
      );
    });

    test('gives up once the device code has expired', () async {
      const expired = DeviceCodeResponse(
        deviceCode: 'dc',
        userCode: 'UC',
        verificationUri: 'u',
        interval: 1,
        // Already in the past, so the loop body never runs.
        expiresIn: -1,
      );
      final auth = authWith(MockClient((_) async => http.Response('{}', 200)));
      await expectLater(
        auth.pollForToken(expired),
        throwsA(
          isA<DeviceAuthException>()
              .having((e) => e.code, 'code', 'expired_token'),
        ),
      );
    });
  });

  test('close() is safe to call', () {
    authWith(MockClient((_) async => http.Response('{}', 200))).close();
  });

  test('constructs with a real http client and default scope', () {
    final auth = GitHubDeviceAuth(clientId: 'cid')..close();
    expect(auth.scope, 'repo');
  });

  test('polls the overridden token endpoint', () async {
    late Uri seen;
    final auth = GitHubDeviceAuth(
      clientId: 'cid',
      tokenUrl: 'http://127.0.0.1:9/gh/auth/device/poll',
      httpClient: MockClient((req) async {
        seen = req.url;
        return http.Response(jsonEncode({'access_token': 'tok'}), 200);
      }),
      delay: noDelay,
    );

    await auth.pollForToken(
      const DeviceCodeResponse(
        deviceCode: 'dc',
        userCode: 'UC',
        verificationUri: 'u',
        interval: 1,
        expiresIn: 60,
      ),
    );

    expect(seen.toString(), 'http://127.0.0.1:9/gh/auth/device/poll');
  });
}
