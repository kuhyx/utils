/// One-tap Google sign-in: the `google_sign_in` plugin call, owned once.
///
/// Why it lives here and not in `crdt_sync`: that package is pure Dart on
/// purpose, because the same library runs on Linux desktop and headless under
/// systemd, where `google_sign_in` does not exist. It only ever receives a
/// token string through a closure -- see `signInWithGoogle`, which takes a
/// `tokenFetcher`. This file is that closure.
///
/// Why it lives here and not in each app: five apps had copied it, and
/// `home_inventory`'s copy was byte-identical to `todo`'s. Copying it a sixth
/// time is the mistake this package exists to prevent.
library;

import 'dart:developer';

import 'package:crdt_sync_flutter/src/google_platform.dart' as platform_gate;
import 'package:google_sign_in/google_sign_in.dart';

/// Whether this build can sign in with Google programmatically.
///
/// Two conjuncts, both load-bearing:
///
/// * the platform must ship the flow (see `google_platform.dart`);
/// * [serverClientId] must be non-empty. A build that forgot the constant
///   would otherwise show a button that always reports "cancelled" and send
///   you debugging the OAuth console for a missing string.
///
/// Takes the id rather than reading a package-level const so the second check
/// cannot be dropped by a consuming app: the only way to ask the question is
/// to supply the value the answer depends on.
bool googleSignInSupported(String serverClientId) =>
    platform_gate.googleSignInSupported && serverClientId.isNotEmpty;

/// Returns a Google ID token for the signed-in account, or null.
///
/// Null rather than throwing when the user dismisses the picker: cancelling is
/// an ordinary outcome, and the caller falls back to the password path.
///
/// [serverClientId] must be the project's **Web** OAuth client id -- Android
/// must request a token minted for the web client, and an Android client id
/// yields a token Firebase rejects with `audience mismatch`.
///
/// [signInFn] exists for tests, which cannot reach the plugin's platform
/// channel; when supplied it replaces the plugin entirely.
Future<String?> googleIdToken({
  required String serverClientId,
  Future<String?> Function()? signInFn,
}) async {
  if (signInFn != null) return signInFn();
  if (serverClientId.isEmpty) {
    log(
      'Google sign-in unavailable: no server client id was compiled in; '
      'falling back to the password path',
      level: 900,
    );
    return null;
  }
  // The plugin reaches the OS account picker through a platform channel,
  // which `flutter test` has no binding for. Everything above this point is
  // pure Dart and is covered.
  // coverage:ignore-start
  try {
    await GoogleSignIn.instance.initialize(serverClientId: serverClientId);
    if (!GoogleSignIn.instance.supportsAuthenticate()) {
      log(
        'Google sign-in is not available on this platform; falling back to '
        'the password path',
        level: 900,
      );
      return null;
    }
    final account = await GoogleSignIn.instance.authenticate();
    return account.authentication.idToken;
  } on GoogleSignInException catch (error, stackTrace) {
    // Includes the user simply dismissing the picker, which is not an error
    // worth surfacing -- but log it, because a *configuration* failure
    // (unregistered SHA-1, wrong client id) arrives through the same path and
    // is otherwise indistinguishable from "the user changed their mind".
    log(
      'Google sign-in did not complete',
      level: 900,
      error: error,
      stackTrace: stackTrace,
    );
    return null;
  }
  // coverage:ignore-end
}
