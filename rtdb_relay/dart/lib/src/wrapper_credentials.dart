/// Desktop sign-in without Google in the browser (todo's pattern).
///
/// The desktop app is the web build in a Chrome `--app` window, served by the
/// app's PC server (e.g. the tutor's). Google Identity Services cannot sign in
/// programmatically there, and nothing outside the Chrome profile can write its
/// storage. So the server hands the page the PC's own seeded session (e.g.
/// `~/.config/tutor/firebase_auth.json`, written by crdt-sync's
/// `link_google.py`) ONCE, at `<app>/sync-credentials`, and the page keeps it
/// in its own credential store from then on.
///
/// The e2e passphrase comes the same way (`<app>/sync-passphrase`, the PC's
/// `~/.config/crdt-sync/password`), asked for only while the key is locked.
library;

import 'dart:convert';
import 'dart:developer';

import 'package:crdt_sync/crdt_sync.dart'
    show FirebaseCredentialStore, FirebaseCredentials;
import 'package:http/http.dart' as http;

/// Route, relative to the app's base URL (`/app/sync-credentials`).
const kSyncCredentialsRoute = 'sync-credentials';

/// Route, relative to the app's base URL (`/app/sync-passphrase`).
const kSyncPassphraseRoute = 'sync-passphrase';

/// The crdt-sync passphrase the wrapper at [base] hands out, or null when it
/// has none to give (404, malformed, empty, no wrapper at all).
Future<String?> fetchWrapperPassphrase({
  required Uri base,
  required http.Client client,
}) async {
  try {
    final res = await client.get(base.resolve(kSyncPassphraseRoute));
    if (res.statusCode != 200) return null;
    final body = jsonDecode(utf8.decode(res.bodyBytes));
    final secret = body is Map<String, dynamic> ? body['passphrase'] : null;
    return secret is String && secret.isNotEmpty ? secret : null;
  } on Object catch (error) {
    log('wrapper passphrase unavailable', level: 800, error: error);
    return null;
  }
}

/// The Firebase uid inside [idToken] (JWT `user_id`, else `sub`), or null.
String? uidOfIdToken(String idToken) {
  final parts = idToken.split('.');
  if (parts.length != 3) return null;
  try {
    final payload = jsonDecode(
      utf8.decode(base64Url.decode(base64Url.normalize(parts[1]))),
    );
    if (payload is! Map<String, dynamic>) return null;
    final uid = payload['user_id'] ?? payload['sub'];
    return uid is String ? uid : null;
  } on FormatException {
    return null;
  }
}

/// Fetches the seeded session from the wrapper at [base] and saves it into
/// [store]. True when adopted. Refuses a session for any uid but
/// [expectedUid]: adopting bypasses the sign-in's wrong-account guard, so
/// the same check is made here.
Future<bool> adoptWrapperCredentials({
  required Uri base,
  required http.Client client,
  required FirebaseCredentialStore store,
  required String expectedUid,
}) async {
  try {
    final res = await client.get(base.resolve(kSyncCredentialsRoute));
    if (res.statusCode != 200) return false;
    final body = jsonDecode(utf8.decode(res.bodyBytes));
    if (body is! Map<String, dynamic> ||
        body['id_token'] is! String ||
        body['refresh_token'] is! String ||
        body['expires_at'] is! String) {
      log('wrapper credentials malformed; not adopted', level: 900);
      return false;
    }
    final uid = uidOfIdToken(body['id_token'] as String);
    if (uid != expectedUid) {
      log('wrapper credentials are for another account', level: 1000);
      return false;
    }
    await store.save(FirebaseCredentials.fromJson(body));
    return true;
  } on Object catch (error) {
    // `on Object`: no wrapper at all (Android: `Uri.base` is file:///, an
    // ArgumentError) or a network error both mean "not adopted".
    log('wrapper credentials unavailable', level: 800, error: error);
    return false;
  }
}
