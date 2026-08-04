/// A [FirebaseCredentialStore] backed by an injected key-value secret store.
///
/// Every Flutter consumer of this package already keeps its GitHub token in
/// `flutter_secure_storage` (Android Keystore / libsecret), which is exactly
/// where a Firebase refresh token belongs too: it is the long-lived secret,
/// while ID tokens expire in about an hour.
///
/// This library deliberately does **not** depend on `flutter_secure_storage`
/// itself -- it is a pure Dart package, and pulling in a Flutter plugin would
/// make it unusable from the command-line tools and from plain `dart test`.
/// The app passes read/write/delete closures instead, which is a two-line
/// adapter at the call site and keeps this file testable with no plugin and
/// no platform channel.
library;

import 'dart:convert';

import 'firebase_auth_rest.dart';

/// Reads a secret by key, returning null when absent.
typedef SecretReader = Future<String?> Function(String key);

/// Writes a secret under a key.
typedef SecretWriter = Future<void> Function(String key, String value);

/// Deletes a secret by key.
typedef SecretDeleter = Future<void> Function(String key);

/// Persists Firebase credentials through a platform secret store.
///
/// Usage from a Flutter app, where `_secure` is a `FlutterSecureStorage`:
///
/// ```dart
/// SecureCredentialStore(
///   read: (k) => _secure.read(key: k),
///   write: (k, v) => _secure.write(key: k, value: v),
///   delete: (k) => _secure.delete(key: k),
/// )
/// ```
class SecureCredentialStore implements FirebaseCredentialStore {
  SecureCredentialStore({
    required this.read,
    required this.write,
    required this.delete,
    this.key = defaultKey,
  });

  /// Where the credentials live in the secret store.
  ///
  /// Namespaced away from each app's `sync.token` (its GitHub PAT) so the two
  /// can coexist for the whole mirrored cutover period.
  static const defaultKey = 'firebase.credentials';

  /// Reads the credentials blob from the platform secret store.
  final SecretReader read;

  /// Writes the credentials blob to the platform secret store.
  final SecretWriter write;

  /// Removes the credentials blob from the platform secret store.
  final SecretDeleter delete;

  /// The secret-store key used for the credentials blob.
  final String key;

  /// Returns the stored credentials, or null if absent or unreadable.
  ///
  /// A corrupt or half-written value reads as "not signed in" rather than
  /// throwing: the caller's next step is to sign in again, which repairs it.
  /// Failing here instead would leave an app permanently unable to sync with
  /// no way back short of a reinstall.
  @override
  Future<FirebaseCredentials?> load() async {
    final String? raw;
    try {
      raw = await read(key);
    } on Exception {
      return null;
    }
    if (raw == null || raw.isEmpty) return null;
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map<String, dynamic>) return null;
      return FirebaseCredentials.fromJson(decoded);
    } on FormatException {
      return null;
    } on TypeError {
      return null;
    }
  }

  @override
  Future<void> save(FirebaseCredentials credentials) =>
      write(key, jsonEncode(credentials.toJson()));

  @override
  Future<void> clear() => delete(key);
}
