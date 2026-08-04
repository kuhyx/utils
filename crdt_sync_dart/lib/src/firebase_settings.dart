/// Per-device Firebase sign-in settings, split by what is safe to publish.
///
/// Every repo in this fleet is **public**, so the split is not cosmetic:
///
/// * [apiKey] and [databaseUrl] identify the *project*. The Web API key is a
///   public identifier by design -- it ships inside every Android APK, and
///   the security rules, not the key, are what protect the data. Baking these
///   into source is safe and keeps a reinstall zero-setup.
/// * The account [email], its `uid` and its password identify **a person**.
///   Those must never reach a public repo, so they are entered once per
///   device and kept in the platform keystore alongside the refresh token.
///
/// The uid deliberately does not appear here at all. Nothing client-side
/// needs it: the security rules compare `auth.uid` server-side, so a wrong
/// account is refused by the database rather than by a local check.
library;

import 'dart:convert';

import 'firebase_config.dart';

/// The shared project's public identifiers.
///
/// [databaseUrl] is the **regional** host. The plain `*.firebaseio.com` form
/// answers 404 with a `correctUrl` body rather than an obvious error, so a
/// wrong value here reads like an auth failure and wastes a debugging session.
class FirebaseProject {
  const FirebaseProject({required this.apiKey, required this.databaseUrl});

  /// Parses the project half of a `firebase.json`.
  factory FirebaseProject.fromJson(Map<String, dynamic> json) =>
      FirebaseProject(
        apiKey: json['apiKey'] as String,
        databaseUrl: json['databaseUrl'] as String,
      );

  /// Public project identifier; ships in the APK by design.
  final String apiKey;

  /// The regional Realtime Database origin, no trailing slash.
  final String databaseUrl;

  /// Combines this project with a per-device [email] into a full config.
  ///
  /// `projectId` and `uid` are filled with empty strings: neither is used by
  /// the REST client, and the uid in particular is checked server-side by the
  /// security rules, so carrying a copy of it in the app would add a way to
  /// be wrong without adding any protection.
  FirebaseConfig configFor(String email) => FirebaseConfig(
    apiKey: apiKey,
    databaseUrl: databaseUrl,
    projectId: '',
    uid: '',
    email: email,
  );
}

/// The account half: entered per device, never committed.
///
/// Stored as one blob in the platform keystore next to the refresh token, so
/// a reinstall asks for it once and nothing identifying is written to
/// `SharedPreferences`, where it would sit in plaintext.
class FirebaseAccount {
  const FirebaseAccount({required this.email, required this.password});

  /// Reads an account blob previously written by [toJsonString].
  ///
  /// Returns null for absent, empty, corrupt or wrong-shaped values: the
  /// caller's next step is to ask for the credentials again, which repairs
  /// it. Throwing instead would leave sync permanently unusable.
  static FirebaseAccount? tryParse(String? raw) {
    if (raw == null || raw.isEmpty) return null;
    final Object? decoded;
    try {
      decoded = jsonDecode(raw);
    } on FormatException {
      return null;
    }
    if (decoded is! Map<String, dynamic>) return null;
    final email = decoded['email'];
    final password = decoded['password'];
    if (email is! String || password is! String) return null;
    if (email.isEmpty || password.isEmpty) return null;
    return FirebaseAccount(email: email, password: password);
  }

  /// The sync account's email address.
  final String email;

  /// The sync account's password. Keystore only -- never prefs, never source.
  final String password;

  /// Serializes for the keystore.
  String toJsonString() => jsonEncode({'email': email, 'password': password});
}

/// Where the account blob lives in the platform secret store.
///
/// Namespaced away from `sync.token` (each app's GitHub PAT) and from
/// `firebase.credentials` (the refresh token), so all three coexist for the
/// whole mirrored cutover.
const kFirebaseAccountKey = 'firebase.account';
