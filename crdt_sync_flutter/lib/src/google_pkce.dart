/// The pure half of the desktop loopback OAuth flow: PKCE, URL building and
/// redirect parsing.
///
/// Split from `google_desktop_sign_in.dart` deliberately. That file binds a
/// socket, opens a browser and posts to Google -- none of which `flutter
/// test` can reach. Everything in *this* file is a pure function over
/// strings, so the logic that is easy to get wrong (the challenge derivation,
/// the state check, the error branch of the redirect) is fully covered
/// without a single suppression.
library;

import 'dart:convert';
import 'dart:math';

import 'package:crypto/crypto.dart';

/// Google's authorization endpoint for the installed-app flow.
const String kGoogleAuthEndpoint =
    'https://accounts.google.com/o/oauth2/v2/auth';

/// Google's token endpoint.
const String kGoogleTokenEndpoint = 'https://oauth2.googleapis.com/token';

/// Characters permitted in a PKCE `code_verifier` (RFC 7636 unreserved set).
const String _verifierAlphabet =
    'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~';

/// A PKCE verifier/challenge pair plus the CSRF `state` for one attempt.
class PkcePair {
  /// Creates a pair from its parts. Prefer [PkcePair.generate].
  const PkcePair({
    required this.verifier,
    required this.challenge,
    required this.state,
  });

  /// Derives a pair from [verifier] and [state], computing the S256
  /// challenge. Separate from [generate] so tests can pin the randomness.
  factory PkcePair.fromVerifier(String verifier, String state) => PkcePair(
    verifier: verifier,
    challenge: _base64Url(sha256.convert(ascii.encode(verifier)).bytes),
    state: state,
  );

  /// Generates a fresh pair. [random] is injectable for deterministic tests.
  factory PkcePair.generate({Random? random}) {
    final rng = random ?? Random.secure();
    return PkcePair.fromVerifier(
      _randomString(rng, 64),
      _randomString(rng, 32),
    );
  }

  /// The high-entropy secret held back until the token exchange.
  final String verifier;

  /// The S256 hash of [verifier], sent in the authorization URL.
  final String challenge;

  /// Opaque value echoed by Google, checked to reject a forged redirect.
  final String state;
}

String _randomString(Random rng, int length) => List.generate(
  length,
  (_) => _verifierAlphabet[rng.nextInt(_verifierAlphabet.length)],
).join();

/// Base64url without padding, as PKCE requires.
String _base64Url(List<int> bytes) =>
    base64Url.encode(bytes).replaceAll('=', '');

/// Builds the URL the user's browser opens to approve the sign-in.
///
/// [redirectPort] is the loopback port already bound -- Google requires the
/// redirect to be `http://127.0.0.1:<port>` for a Desktop client, and binding
/// first means the port in the URL is the port actually listening.
Uri buildAuthUrl({
  required String clientId,
  required int redirectPort,
  required PkcePair pkce,
}) => Uri.parse(kGoogleAuthEndpoint).replace(
  queryParameters: <String, String>{
    'client_id': clientId,
    'redirect_uri': redirectUriFor(redirectPort),
    'response_type': 'code',
    // openid+email is the minimum that yields an id_token carrying the
    // address; Firebase's signInWithIdp needs the id_token, not the access
    // token, so no broader scope is requested.
    'scope': 'openid email',
    'code_challenge': pkce.challenge,
    'code_challenge_method': 'S256',
    'state': pkce.state,
  },
);

/// The loopback redirect URI for [port].
///
/// `127.0.0.1` rather than `localhost`: Google's installed-app documentation
/// specifies the literal address, and a machine resolving `localhost` to `::1`
/// would otherwise present a URI the console never matched.
String redirectUriFor(int port) => 'http://127.0.0.1:$port';

/// Outcome of parsing Google's redirect back to the loopback server.
class RedirectResult {
  /// Creates a result. Exactly one of [code] and [error] is non-null.
  const RedirectResult({this.code, this.error});

  /// The authorization code, when the user approved.
  final String? code;

  /// Why the attempt did not yield a code, when it did not.
  final String? error;
}

/// Reads Google's redirect [uri], checking it against the expected [state].
///
/// Returns an error result rather than throwing: every failure here ends the
/// same way -- fall back to the password path -- and the caller should not
/// have to distinguish a denial from a forgery to do that.
RedirectResult parseRedirect(Uri uri, {required String expectedState}) {
  final params = uri.queryParameters;
  final returnedState = params['state'];
  if (returnedState != expectedState) {
    // Either a stale redirect from an earlier attempt or a forged request
    // aimed at the loopback port; neither may be treated as this sign-in.
    return const RedirectResult(error: 'state mismatch');
  }
  final error = params['error'];
  if (error != null) return RedirectResult(error: error);
  final code = params['code'];
  if (code == null || code.isEmpty) {
    return const RedirectResult(error: 'no authorization code in redirect');
  }
  return RedirectResult(code: code);
}

/// Form body for exchanging [code] at [kGoogleTokenEndpoint].
Map<String, String> tokenExchangeBody({
  required String clientId,
  required String code,
  required int redirectPort,
  required String verifier,
}) => <String, String>{
  'client_id': clientId,
  'code': code,
  'code_verifier': verifier,
  'grant_type': 'authorization_code',
  'redirect_uri': redirectUriFor(redirectPort),
};

/// Pulls the `id_token` out of Google's token-endpoint response [body].
///
/// Returns null on any shape that does not carry one, including an error
/// response -- the caller falls back to the password path either way.
String? idTokenFromResponse(String body) {
  final decoded = jsonDecode(body);
  if (decoded is! Map<String, dynamic>) return null;
  final token = decoded['id_token'];
  return token is String && token.isNotEmpty ? token : null;
}
