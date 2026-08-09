/// Provisioning the sync account on a desktop (Chrome web) build.
library;

import 'dart:convert';

import 'package:http/http.dart' as http;

import 'firebase_settings.dart';

/// The wrapper route that serves this machine's shared sync account.
///
/// Desktop builds of these apps are Flutter **web** running in a Chrome
/// `--app` window, so `FlutterSecureStorage` resolves to the web backend:
/// AES-encrypted `localStorage`, keyed inside the browser profile. Nothing
/// outside that profile can write it -- not `secret-tool` (wrong store), not
/// a Dart CLI (`flutter_secure_storage` is a Flutter plugin and will not even
/// import on the VM). The only process that can both read the filesystem and
/// reach the page is the wrapper that serves it, so the account arrives the
/// same way the GitHub token already does: from the wrapper, never from
/// source and never from prefs.
const kSyncAccountPath = '/sync-account';

/// Env var a wrapper checks before serving [kSyncAccountPath].
///
/// Off by default. The route hands out a credential with database write
/// access to anything that can reach the wrapper's port, so it is opt-in per
/// launch rather than always-on: set it once to provision a new desktop
/// install, then launch normally.
const kSyncAccountEnvVar = 'CRDT_SYNC_SERVE_ACCOUNT';

/// Marker written when the user disconnects, suppressing re-provisioning.
///
/// Without it, "Disconnect" would delete the stored account and the next
/// launch would silently adopt it again from the wrapper, making the button
/// look broken.
const kSyncAccountOptOutKey = 'firebase.account.optOut';

/// Fetches the shared account the wrapper holds, or null.
///
/// Returns null for every failure -- route absent (the normal case, since it
/// is opt-in), wrapper not running, malformed body -- because the caller's
/// fallback is simply "not configured", which the settings screen already
/// handles by asking the user.
///
/// Args:
///   base: Origin of the local wrapper, e.g. `http://localhost:8730`.
///   client: Injected for tests.
Future<FirebaseAccount?> accountFromWrapper(
  Uri base, {
  http.Client? client,
}) async {
  final httpClient = client ?? http.Client();
  try {
    final response = await httpClient.get(base.resolve(kSyncAccountPath));
    if (response.statusCode != 200) return null;
    return FirebaseAccount.tryParse(utf8.decode(response.bodyBytes));
  } on Exception {
    return null;
  } finally {
    if (client == null) httpClient.close();
  }
}
