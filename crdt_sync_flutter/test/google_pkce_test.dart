import 'dart:convert';
import 'dart:math';

import 'package:crdt_sync_flutter/crdt_sync_flutter.dart';
import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('PkcePair', () {
    test('derives the S256 challenge of the verifier', () {
      final pair = PkcePair.fromVerifier('abc123', 'state-1');
      final expected = base64Url
          .encode(sha256.convert(ascii.encode('abc123')).bytes)
          .replaceAll('=', '');
      expect(pair.challenge, expected);
      expect(pair.verifier, 'abc123');
      expect(pair.state, 'state-1');
    });

    test('challenge carries no base64 padding', () {
      // '=' in a query parameter survives, but RFC 7636 requires it stripped
      // and Google rejects a padded challenge.
      expect(PkcePair.fromVerifier('a', 's').challenge, isNot(contains('=')));
    });

    test('generate produces a 64-char verifier and 32-char state', () {
      final pair = PkcePair.generate(random: Random(7));
      expect(pair.verifier, hasLength(64));
      expect(pair.state, hasLength(32));
      expect(pair.challenge, isNotEmpty);
    });

    test('generate is seedable, and unseeded still yields a pair', () {
      expect(
        PkcePair.generate(random: Random(1)).verifier,
        PkcePair.generate(random: Random(1)).verifier,
      );
      expect(PkcePair.generate().verifier, hasLength(64));
    });

    test('verifier uses only the unreserved alphabet', () {
      final pair = PkcePair.generate(random: Random(3));
      expect(RegExp(r'^[A-Za-z0-9\-._~]+$').hasMatch(pair.verifier), isTrue);
    });
  });

  group('buildAuthUrl', () {
    final pkce = PkcePair.fromVerifier('verifier', 'the-state');
    final url = buildAuthUrl(clientId: 'cid', redirectPort: 4321, pkce: pkce);

    test('targets Google and carries the PKCE challenge', () {
      expect(url.toString(), startsWith(kGoogleAuthEndpoint));
      expect(url.queryParameters['code_challenge'], pkce.challenge);
      expect(url.queryParameters['code_challenge_method'], 'S256');
    });

    test('asks for a code against the bound loopback port', () {
      expect(url.queryParameters['response_type'], 'code');
      expect(url.queryParameters['redirect_uri'], 'http://127.0.0.1:4321');
      expect(url.queryParameters['client_id'], 'cid');
      expect(url.queryParameters['state'], 'the-state');
    });

    test('requests openid email, the minimum yielding an id_token', () {
      expect(url.queryParameters['scope'], 'openid email');
    });
  });

  test('redirectUriFor uses the literal loopback address', () {
    // Not `localhost`: a host resolving it to ::1 would present a URI the
    // OAuth console never matched.
    expect(redirectUriFor(80), 'http://127.0.0.1:80');
  });

  group('parseRedirect', () {
    Uri uri(Map<String, String> params) =>
        Uri.parse('http://127.0.0.1:1/').replace(queryParameters: params);

    test('returns the code when state matches', () {
      final result = parseRedirect(
        uri({'code': 'abc', 'state': 's'}),
        expectedState: 's',
      );
      expect(result.code, 'abc');
      expect(result.error, isNull);
    });

    test('rejects a mismatched state without reading the code', () {
      final result = parseRedirect(
        uri({'code': 'abc', 'state': 'other'}),
        expectedState: 's',
      );
      expect(result.code, isNull);
      expect(result.error, 'state mismatch');
    });

    test('rejects a redirect carrying no state at all', () {
      final result = parseRedirect(uri({'code': 'abc'}), expectedState: 's');
      expect(result.error, 'state mismatch');
    });

    test('surfaces Google\'s error parameter', () {
      final result = parseRedirect(
        uri({'error': 'access_denied', 'state': 's'}),
        expectedState: 's',
      );
      expect(result.code, isNull);
      expect(result.error, 'access_denied');
    });

    test('reports a redirect with neither code nor error', () {
      final result = parseRedirect(uri({'state': 's'}), expectedState: 's');
      expect(result.error, 'no authorization code in redirect');
    });

    test('treats an empty code as no code', () {
      final result = parseRedirect(
        uri({'code': '', 'state': 's'}),
        expectedState: 's',
      );
      expect(result.error, 'no authorization code in redirect');
    });

    test('constructs directly with neither field', () {
      const result = RedirectResult();
      expect(result.code, isNull);
      expect(result.error, isNull);
    });
  });

  test('tokenExchangeBody sends the verifier, not the challenge', () {
    final body = tokenExchangeBody(
      clientId: 'cid',
      code: 'the-code',
      redirectPort: 9,
      verifier: 'the-verifier',
    );
    expect(body['code_verifier'], 'the-verifier');
    expect(body['grant_type'], 'authorization_code');
    expect(body['code'], 'the-code');
    expect(body['client_id'], 'cid');
    expect(body['redirect_uri'], 'http://127.0.0.1:9');
  });

  group('idTokenFromResponse', () {
    test('reads the id_token', () {
      expect(idTokenFromResponse('{"id_token":"tok"}'), 'tok');
    });

    test('returns null for an error response', () {
      expect(idTokenFromResponse('{"error":"invalid_grant"}'), isNull);
    });

    test('returns null for an empty id_token', () {
      expect(idTokenFromResponse('{"id_token":""}'), isNull);
    });

    test('returns null for a non-string id_token', () {
      expect(idTokenFromResponse('{"id_token":42}'), isNull);
    });

    test('returns null for a non-object body', () {
      expect(idTokenFromResponse('[]'), isNull);
    });
  });
}
