/// Firebase Authentication over its REST API, with no FlutterFire dependency.
///
/// The official `firebase_auth` plugin ships iOS/Android/Web/macOS only --
/// there is no Linux desktop support -- but these apps run on Linux desktop
/// *and* Android, and one (`wake_alarm`) runs headless under systemd. The
/// REST endpoints are plain HTTPS and behave identically everywhere, so this
/// is the only auth path that covers every target.
library;

import 'dart:convert';

import 'package:http/http.dart' as http;

import 'firebase_auth_error.dart';
import 'firebase_credentials.dart';

const _signInBase = 'https://identitytoolkit.googleapis.com/v1';
const _refreshBase = 'https://securetoken.googleapis.com/v1';

/// Signs in and keeps a valid ID token available, refreshing as needed.
///
/// [apiKey] is the project's public Web API key -- not a secret, and safe to
/// ship inside an APK. The actual credential is the refresh token held by
/// [store]. A service-account key is deliberately **not** used: it would
/// bypass the security rules entirely and is trivially extractable from an
/// installed app.
class FirebaseTokenProvider {
  FirebaseTokenProvider({
    required this.apiKey,
    required this.store,
    http.Client? httpClient,
    DateTime Function()? clock,
  }) : _http = httpClient ?? http.Client(),
       _clock = clock ?? DateTime.now;

  final String apiKey;

  /// Where the refresh token lives between runs. Public so a settings screen
  /// can swap in the platform-appropriate backing store.
  final FirebaseCredentialStore store;
  final http.Client _http;
  final DateTime Function() _clock;

  FirebaseCredentials? _cached;

  /// Exchanges an email/password for a session and persists it.
  ///
  /// Called once per device from a settings screen or a setup command; every
  /// later run reuses the stored refresh token.
  Future<void> signIn({required String email, required String password}) async {
    final body = await _post(
      Uri.parse('$_signInBase/accounts:signInWithPassword?key=$apiKey'),
      {'email': email, 'password': password, 'returnSecureToken': true},
      'sign in',
    );
    await _adopt(
      idToken: body['idToken'] as String,
      refreshToken: body['refreshToken'] as String,
      expiresInSeconds: body['expiresIn'] as String,
    );
  }

  /// Exchanges a Google ID token for a session and persists it.
  ///
  /// This is the one-tap path: a fresh install signs in by picking a Google
  /// account instead of typing the sync account's long password.
  ///
  /// **The Google identity must already be linked to the sync account.** The
  /// security rules pin one uid, so a Google identity that is *not* linked
  /// signs in as a different uid, which authenticates fine and is then denied
  /// every read and write -- a sync that silently never syncs. Link once from
  /// the PC with `crdt-sync/tool/link_google.py`, which asserts the uid.
  ///
  /// [idToken] comes from the platform's Google sign-in flow. The library
  /// deliberately does not depend on `google_sign_in`: that plugin has no
  /// Linux desktop support, and this package has to keep working headless.
  /// The app fetches the token and passes it in.
  ///
  /// [expectedUid], when given, is asserted against the uid Firebase returns
  /// and a mismatch throws without storing anything. **Pass it.** Unlike a
  /// password -- where a wrong credential is simply rejected -- an unlinked
  /// Google identity is *accepted*: `signInWithIdp` signs in **or signs up**,
  /// so picking the wrong account in the phone's account picker silently
  /// creates a second user. Without this check that session persists, every
  /// read and write is denied by the rules, and the failure survives
  /// relaunches because the bad refresh token was saved.
  /// Returns the email Google signed in as, which the caller needs: on a
  /// fresh install nothing on the device knows it yet, and that is precisely
  /// the case this path exists for.
  Future<String?> signInWithGoogle({
    required String idToken,
    String? expectedUid,
  }) async {
    final body = await _post(
      Uri.parse('$_signInBase/accounts:signInWithIdp?key=$apiKey'),
      {
        // The IdP credential travels as a form-encoded body, not as JSON --
        // an identitytoolkit quirk, not a mistake.
        'postBody': 'id_token=$idToken&providerId=google.com',
        'requestUri': 'http://localhost',
        'returnSecureToken': true,
      },
      'sign in with Google',
    );
    final uid = body['localId'] as String?;
    if (expectedUid != null && expectedUid.isNotEmpty && uid != expectedUid) {
      // Deliberately before _adopt: nothing is stored, so the device stays
      // unconfigured and the user can retry with the right account.
      throw FirebaseAuthError(
        'signed in as the wrong account: Google resolved to uid $uid, but '
        'this data belongs to $expectedUid. Pick the Google account that was '
        'linked with crdt-sync/tool/link_google.py.',
      );
    }
    await _adopt(
      idToken: body['idToken'] as String,
      refreshToken: body['refreshToken'] as String,
      expiresInSeconds: body['expiresIn'] as String,
    );
    return body['email'] as String?;
  }

  /// Returns a currently-valid ID token, refreshing or failing loudly.
  ///
  /// Throws [FirebaseAuthError] when no session is stored or the refresh
  /// token has been revoked -- never returns a stale token and never
  /// silently no-ops, because a sync that quietly stops syncing is the
  /// failure mode this whole design is trying to avoid.
  Future<String> idToken() async {
    final credentials = _cached ??= await store.load();
    if (credentials == null) {
      throw FirebaseAuthError(
        'not signed in: no stored refresh token for this device',
      );
    }
    if (!credentials.isExpiredAt(_clock())) return credentials.idToken;
    return _refresh(credentials.refreshToken);
  }

  /// Whether this device has a stored session at all.
  ///
  /// Distinguishes "sync is not configured" (fine -- `screen-locker` treats a
  /// missing credential as a normal state) from "sync is configured and
  /// broken" (an error).
  Future<bool> hasSession() async => (_cached ??= await store.load()) != null;

  /// Whether [error] means the refresh token is permanently dead.
  ///
  /// Only these reasons are terminal. A network error or a 5xx must NOT clear
  /// the session: a device that signs itself out every time the wifi drops is
  /// a worse bug than the one this guards against, since recovering needs a
  /// manual sign-in on each device.
  static bool _isRevoked(FirebaseAuthError error) {
    const terminal = [
      'TOKEN_EXPIRED',
      'USER_DISABLED',
      'USER_NOT_FOUND',
      'INVALID_REFRESH_TOKEN',
      'INVALID_GRANT_TYPE',
      'MISSING_REFRESH_TOKEN',
    ];
    return terminal.any(error.message.contains);
  }

  /// Forgets the stored session, so the next [idToken] fails loudly.
  Future<void> signOut() async {
    _cached = null;
    await store.clear();
  }

  Future<String> _refresh(String refreshToken) async {
    final Map<String, dynamic> body;
    try {
      body = await _post(Uri.parse('$_refreshBase/token?key=$apiKey'), {
        'grant_type': 'refresh_token',
        'refresh_token': refreshToken,
      }, 'refresh the session');
    } on FirebaseAuthError catch (error) {
      // A revoked refresh token never becomes valid again, so keeping it is
      // what made a dead device report "Connected" and then fail every sync
      // with TOKEN_EXPIRED. Drop it, so hasSession() answers honestly and the
      // settings screen offers a sign-in instead of a broken banner.
      if (_isRevoked(error)) await signOut();
      rethrow;
    }
    return _adopt(
      idToken: body['id_token'] as String,
      // A refresh may hand back a rotated refresh token; keep the new one.
      refreshToken: body['refresh_token'] as String,
      expiresInSeconds: body['expires_in'] as String,
    );
  }

  Future<String> _adopt({
    required String idToken,
    required String refreshToken,
    required String expiresInSeconds,
  }) async {
    final credentials = FirebaseCredentials(
      idToken: idToken,
      refreshToken: refreshToken,
      expiresAt: _clock().toUtc().add(
        Duration(seconds: int.parse(expiresInSeconds)),
      ),
    );
    _cached = credentials;
    await store.save(credentials);
    return idToken;
  }

  Future<Map<String, dynamic>> _post(
    Uri uri,
    Map<String, Object> payload,
    String what,
  ) async {
    late final http.Response res;
    try {
      res = await _http.post(
        uri,
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(payload),
      );
    } on http.ClientException catch (exc) {
      throw FirebaseAuthError('network error trying to $what: $exc');
    }
    if (res.statusCode < 200 || res.statusCode >= 300) {
      throw FirebaseAuthError(
        'failed to $what: HTTP ${res.statusCode} ${reasonFrom(res.body)}',
      );
    }
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  /// Pulls Google's machine-readable reason (`INVALID_PASSWORD`,
  /// `TOKEN_EXPIRED`, `USER_DISABLED`, ...) out of an error body, so the
  /// thrown message says what actually went wrong instead of just "400".
  void close() => _http.close();
}
