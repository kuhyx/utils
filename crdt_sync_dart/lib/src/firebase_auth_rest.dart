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

import 'remote_store.dart';

const _signInBase = 'https://identitytoolkit.googleapis.com/v1';
const _refreshBase = 'https://securetoken.googleapis.com/v1';

/// Refresh this long before the token actually expires.
///
/// An ID token lives ~1 h. Refreshing early means a tick that starts just
/// under the wire still finishes with a valid token, rather than 401ing
/// halfway through a multi-file push.
const _refreshSkew = Duration(minutes: 5);

/// Raised for an authentication failure the caller must not silently ignore.
///
/// A [RemoteSyncError] so callers that only care about "sync is broken" can
/// catch one type, while a settings screen can single this out to say
/// "your password is wrong" rather than "the network is down".
class FirebaseAuthError extends RemoteSyncError {
  FirebaseAuthError(super.message);
}

/// One device's Firebase session: a short-lived ID token plus the long-lived
/// refresh token that mints the next one.
class FirebaseCredentials {
  FirebaseCredentials({
    required this.idToken,
    required this.refreshToken,
    required this.expiresAt,
  });

  factory FirebaseCredentials.fromJson(Map<String, dynamic> json) =>
      FirebaseCredentials(
        idToken: json['id_token'] as String,
        refreshToken: json['refresh_token'] as String,
        expiresAt: DateTime.parse(json['expires_at'] as String).toUtc(),
      );

  /// The bearer credential for Realtime Database requests. Expires quickly.
  final String idToken;

  /// The long-lived credential. **This is the secret worth protecting** --
  /// store it in `flutter_secure_storage` on Android or a `0600` file on
  /// Linux, never in plain `SharedPreferences`.
  final String refreshToken;

  final DateTime expiresAt;

  /// Whether [idToken] is expired, or close enough that a tick starting now
  /// might outlive it.
  bool isExpiredAt(DateTime now) => !now.add(_refreshSkew).isBefore(expiresAt);

  Map<String, dynamic> toJson() => {
    'id_token': idToken,
    'refresh_token': refreshToken,
    'expires_at': expiresAt.toUtc().toIso8601String(),
  };
}

/// Where a device keeps its [FirebaseCredentials] between runs.
///
/// Abstract because the right answer differs per platform, and one of the
/// callers (`wake_alarm` PC) is a **fresh process every minute** -- without
/// persistence it would re-authenticate 1440 times a day.
abstract interface class FirebaseCredentialStore {
  Future<FirebaseCredentials?> load();
  Future<void> save(FirebaseCredentials credentials);
  Future<void> clear();
}

/// An in-memory [FirebaseCredentialStore], for tests and one-shot scripts.
class InMemoryCredentialStore implements FirebaseCredentialStore {
  InMemoryCredentialStore([this._credentials]);

  FirebaseCredentials? _credentials;

  @override
  Future<FirebaseCredentials?> load() async => _credentials;

  @override
  Future<void> save(FirebaseCredentials credentials) async =>
      _credentials = credentials;

  @override
  Future<void> clear() async => _credentials = null;
}

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
  Future<void> signIn({
    required String email,
    required String password,
  }) async {
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
  Future<bool> hasSession() async =>
      (_cached ??= await store.load()) != null;

  /// Forgets the stored session, so the next [idToken] fails loudly.
  Future<void> signOut() async {
    _cached = null;
    await store.clear();
  }

  Future<String> _refresh(String refreshToken) async {
    final body = await _post(
      Uri.parse('$_refreshBase/token?key=$apiKey'),
      {'grant_type': 'refresh_token', 'refresh_token': refreshToken},
      'refresh the session',
    );
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
        'failed to $what: HTTP ${res.statusCode} ${_reason(res.body)}',
      );
    }
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  /// Pulls Google's machine-readable reason (`INVALID_PASSWORD`,
  /// `TOKEN_EXPIRED`, `USER_DISABLED`, ...) out of an error body, so the
  /// thrown message says what actually went wrong instead of just "400".
  static String _reason(String body) {
    try {
      final decoded = jsonDecode(body);
      if (decoded is Map<String, dynamic>) {
        final error = decoded['error'];
        if (error is Map<String, dynamic>) return '(${error['message']})';
        if (error is String) return '($error)';
      }
    } on FormatException {
      // Non-JSON body (a proxy error page, say): the status code is all the
      // detail there is.
    }
    return '';
  }

  void close() => _http.close();
}
