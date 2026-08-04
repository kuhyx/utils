/// The Dart counterpart to Python's `crdt_sync._config`.
///
/// Both languages talk to one Firebase project as one account, so the shape
/// of the configuration is shared even though where it is *stored* is not:
/// on Linux it is `~/.config/crdt-sync/firebase.json` (mode 0600), while on
/// Android the password and refresh token belong in `flutter_secure_storage`
/// and the file does not exist at all.
///
/// [FirebaseConfig] therefore takes plain values and stays free of `dart:io`,
/// so it works on web and mobile. The platform-specific loading is the app's
/// job -- `crdt_sync_io.dart` provides the desktop half.
library;

import 'dart:convert';

import 'package:http/http.dart' as http;

import 'firebase_auth_rest.dart';
import 'firebase_client.dart';
import 'mirror_store.dart';
import 'remote_store.dart';

/// The shared config is missing a field, or still holds a scaffold placeholder.
class ConfigException implements Exception {
  ConfigException(this.message);

  final String message;

  @override
  String toString() => 'ConfigException: $message';
}

/// Everything needed to reach the shared Firebase project.
///
/// [apiKey] is not a secret: it ships inside the Android APKs, and the
/// security rules are what protect the data. The password is.
class FirebaseConfig {
  const FirebaseConfig({
    required this.apiKey,
    required this.databaseUrl,
    required this.projectId,
    required this.uid,
    required this.email,
  });

  /// Parses the same `firebase.json` the Python side reads.
  ///
  /// Throws [ConfigException] naming the field at fault, because the
  /// alternative is an authentication failure much later with no clue which
  /// value was wrong. Keys prefixed `_comment` are the scaffold's inline
  /// documentation, not configuration, and are ignored.
  factory FirebaseConfig.fromJson(Map<String, dynamic> json) {
    String require(String key) {
      final value = json[key];
      if (value == null || (value is String && value.trim().isEmpty)) {
        throw ConfigException('firebase.json is missing or has empty: $key');
      }
      final text = value.toString();
      if (text.contains('PASTE_')) {
        throw ConfigException(
          'firebase.json still holds the placeholder for: $key',
        );
      }
      return text;
    }

    return FirebaseConfig(
      apiKey: require('apiKey'),
      databaseUrl: require('databaseUrl'),
      projectId: require('projectId'),
      uid: require('uid'),
      email: require('email'),
    );
  }

  /// Parses [text] as the shared config file's contents.
  factory FirebaseConfig.parse(String text) {
    final Object? decoded;
    try {
      decoded = jsonDecode(text);
    } on FormatException catch (error) {
      throw ConfigException(
        'firebase.json is not valid JSON: ${error.message}',
      );
    }
    if (decoded is! Map<String, dynamic>) {
      throw ConfigException('firebase.json must contain a JSON object');
    }
    return FirebaseConfig.fromJson(decoded);
  }

  final String apiKey;
  final String databaseUrl;
  final String projectId;

  /// The uid the security rules pin. A session for any other uid authenticates
  /// fine and is then denied every read and write.
  final String uid;
  final String email;
}

/// Returns a client for [config], signing in only when there is no session.
///
/// The common path costs no authentication round trip: [store] holds the
/// refresh token between launches. Pass the platform-appropriate store --
/// `flutter_secure_storage` on Android, a 0600 file on desktop.
Future<FirebaseRestClient> firebaseClientFor({
  required FirebaseConfig config,
  required FirebaseCredentialStore store,
  String? password,
  http.Client? httpClient,
}) async {
  final auth = FirebaseTokenProvider(
    apiKey: config.apiKey,
    store: store,
    httpClient: httpClient,
  );
  if (await store.load() == null) {
    if (password == null) {
      throw ConfigException(
        'no stored session for ${config.email} and no password given; '
        'sign in once from the settings screen',
      );
    }
    await auth.signIn(email: config.email, password: password);
  }
  return FirebaseRestClient(
    databaseUrl: config.databaseUrl,
    auth: auth,
    httpClient: httpClient,
  );
}

/// Returns a Firebase-primary store that still mirrors to [githubClient].
///
/// What an app uses *during* the cutover: Firebase is authoritative, GitHub is
/// kept in step but never allowed to fail a tick, and reads union both so
/// devices can cut over one at a time. Rolling back is passing [githubClient]
/// straight to `syncLog` again; retiring the mirror is calling
/// [firebaseClientFor] instead. Both are one-line changes at the call site.
Future<MirrorStore> mirrorStoreFor({
  required FirebaseConfig config,
  required FirebaseCredentialStore store,
  required RemoteStore githubClient,
  String? password,
  http.Client? httpClient,
}) async => MirrorStore(
  primary: await firebaseClientFor(
    config: config,
    store: store,
    password: password,
    httpClient: httpClient,
  ),
  mirror: githubClient,
);
