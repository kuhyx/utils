/// One-tap Google sign-in: the `google_account_token` plugin call, owned once.
///
/// Why it lives here and not in `crdt_sync`: that package is pure Dart on
/// purpose, because the same library runs on Linux desktop and headless under
/// systemd, where the Android plugin does not exist. It only ever receives a
/// token string through a closure -- see `signInWithGoogle`, which takes a
/// `tokenFetcher`. This file is that closure.
///
/// Why it lives here and not in each app: five apps had copied it, and
/// `home_inventory`'s copy was byte-identical to `todo`'s. Copying it a sixth
/// time is the mistake this package exists to prevent.
library;

import 'package:crdt_sync_flutter/src/google_platform.dart' as platform_gate;
import 'package:google_account_token/google_account_token.dart' as account;

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
/// Null rather than throwing when the user dismisses the chooser: cancelling
/// is an ordinary outcome, and the caller falls back to the password path.
/// The plugin logs (level 900) every failure, which matters because a
/// *configuration* failure (unregistered SHA-1, wrong client id) arrives
/// through the same path as "the user changed their mind".
///
/// [serverClientId] must be the project's **Web** OAuth client id -- the token
/// is minted for that audience, and an Android client id yields one Firebase
/// rejects with `audience mismatch`.
///
/// [signInFn] exists for tests; when supplied it replaces the plugin entirely.
Future<String?> googleIdToken({
  required String serverClientId,
  Future<String?> Function()? signInFn,
}) async {
  if (signInFn != null) return await signInFn();
  return await account.googleIdToken(serverClientId: serverClientId);
}
