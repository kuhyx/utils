/// Refresh this long before the token actually expires.
///
/// An ID token lives ~1 h. Refreshing early means a tick that starts just
/// under the wire still finishes with a valid token, rather than 401ing
/// halfway through a multi-file push.
const _refreshSkew = Duration(minutes: 5);

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
