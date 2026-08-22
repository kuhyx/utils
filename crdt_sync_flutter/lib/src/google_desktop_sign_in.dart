/// One-tap Google sign-in for desktop, via the OAuth loopback flow.
///
/// `google_sign_in` ships android, ios and web implementations only -- there
/// is no `google_sign_in_linux` -- so a real GTK build cannot use the plugin
/// at all. The installed-app flow replaces it: bind a loopback socket, open
/// the system browser at Google's consent screen, catch the redirect, and
/// exchange the code for an id_token with PKCE. The token is the same shape
/// the plugin returns, so `signInWithGoogle` cannot tell the two apart.
///
/// Everything decision-shaped lives in `google_pkce.dart` and is covered.
/// This file is the I/O: a socket, a browser, one POST.
library;

import 'dart:async';
import 'dart:io';

import 'package:crdt_sync_flutter/src/google_pkce.dart';
import 'package:http/http.dart' as http;
import 'package:url_launcher/url_launcher.dart';

/// Binds a loopback server. Injectable so tests need no real socket.
typedef ServerBinder = Future<HttpServer> Function();

/// Opens [url] in the user's browser. Injectable for the same reason.
typedef BrowserLauncher = Future<bool> Function(Uri url);

/// How long to wait for the user to finish in the browser before giving up.
///
/// Generous: it spans reading a consent screen and possibly a password
/// prompt. The server is closed either way, so a timeout leaks nothing.
const Duration kDesktopSignInTimeout = Duration(minutes: 3);

/// What the browser shows after the redirect lands.
///
/// Served as the response to Google's redirect, because the alternative is
/// leaving the user staring at a blank page wondering whether it worked.
const String kSuccessPage = '''
<!doctype html><meta charset="utf-8">
<title>Signed in</title>
<body style="font-family:system-ui;background:#1B1D21;color:#E8E8E8;
display:grid;place-items:center;height:100vh;margin:0">
<main style="text-align:center">
<h1 style="font-weight:600">Signed in</h1>
<p>You can close this tab and return to the app.</p>
</main>''';

Future<HttpServer> _bindLoopback() =>
    // Port 0 lets the OS pick a free port; the Desktop OAuth client type
    // accepts any loopback port, so nothing needs registering per port.
    HttpServer.bind(InternetAddress.loopbackIPv4, 0);

// url_launcher reaches a platform channel, which `flutter test` has no
// binding for -- the same exemption the Android plugin call takes. The
// injected `launcher` seam above is what the suite exercises instead.
// coverage:ignore-start
Future<bool> _launchInBrowser(Uri url) =>
    launchUrl(url, mode: LaunchMode.externalApplication);
// coverage:ignore-end

/// Signs in through the browser and returns a Google ID token, or null.
///
/// Null on every ordinary failure -- the user closing the tab, denying
/// consent, or the timeout elapsing -- because they all end the same way:
/// the caller falls back to the password path.
///
/// [clientId] must be a **Desktop**-type OAuth client. The Web client id used
/// for the Android flow will be rejected here, and a Desktop client is the
/// only type permitted to redirect to loopback.
Future<String?> googleDesktopIdToken({
  required String clientId,
  ServerBinder binder = _bindLoopback,
  BrowserLauncher launcher = _launchInBrowser,
  http.Client? httpClient,
  Duration timeout = kDesktopSignInTimeout,
  PkcePair? pkce,
}) async {
  if (clientId.isEmpty) return null;
  final pair = pkce ?? PkcePair.generate();
  final server = await binder();
  // Read once, up front: `server.port` throws HttpException once the socket
  // is closed, and the exchange below outlives the listening phase.
  final port = server.port;
  final client = httpClient ?? http.Client();
  try {
    final opened = await launcher(
      buildAuthUrl(
        clientId: clientId,
        redirectPort: port,
        pkce: pair,
      ),
    );
    // No browser means no redirect will ever arrive: fail now rather than
    // holding the socket open for the full timeout.
    if (!opened) return null;
    final code = await _awaitRedirect(server, pair.state, timeout);
    if (code == null) return null;
    // Awaited, not returned bare: the finally below closes the server and the
    // http client, and an unawaited return would let that race the exchange.
    return await _exchange(
      client: client,
      clientId: clientId,
      code: code,
      port: port,
      verifier: pair.verifier,
    );
  } finally {
    await server.close(force: true);
    if (httpClient == null) client.close();
  }
}

/// Waits for Google's redirect and returns the authorization code, or null.
Future<String?> _awaitRedirect(
  HttpServer server,
  String expectedState,
  Duration timeout,
) async {
  final completer = Completer<String?>();
  final subscription = server.listen((request) async {
    final result = parseRedirect(request.uri, expectedState: expectedState);
    request.response
      ..statusCode = result.code != null ? HttpStatus.ok : HttpStatus.badRequest
      ..headers.contentType = ContentType.html
      ..write(result.code != null ? kSuccessPage : 'Sign-in failed. ');
    await request.response.close();
    if (!completer.isCompleted) completer.complete(result.code);
  });
  try {
    return await completer.future.timeout(timeout, onTimeout: () => null);
  } finally {
    await subscription.cancel();
  }
}

/// Exchanges [code] for an ID token.
Future<String?> _exchange({
  required http.Client client,
  required String clientId,
  required String code,
  required int port,
  required String verifier,
}) async {
  final response = await client.post(
    Uri.parse(kGoogleTokenEndpoint),
    body: tokenExchangeBody(
      clientId: clientId,
      code: code,
      redirectPort: port,
      verifier: verifier,
    ),
  );
  if (response.statusCode != HttpStatus.ok) return null;
  return idTokenFromResponse(response.body);
}
