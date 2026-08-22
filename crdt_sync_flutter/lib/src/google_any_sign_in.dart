/// Picks the right Google sign-in flow for the platform.
///
/// Two flows exist because one is not enough: `google_sign_in` ships android,
/// ios and web implementations only -- there is no `google_sign_in_linux` --
/// so a real GTK desktop build reaches Google through the OAuth loopback flow
/// instead. Both yield a Google ID token of the same shape, so
/// `signInWithGoogle` cannot tell them apart.
///
/// This file owns the choice so that consuming apps do not each re-derive it,
/// which is the whole reason this package exists.
library;

import 'package:crdt_sync_flutter/src/google_desktop_sign_in.dart';
import 'package:crdt_sync_flutter/src/google_platform.dart' as platform_gate;
import 'package:crdt_sync_flutter/src/google_sign_in.dart';

/// Whether Google sign-in can succeed here through *either* flow.
///
/// Pass this to `SyncSettingsScreen.googleAvailable`. Each half is gated on
/// its own client id being present, so an app that configured only one still
/// gets a button exactly where that one works.
///
/// [serverClientId] is the **Web** OAuth client id (the audience for the
/// plugin's tokens); [desktopClientId] is a **Desktop**-type client, the only
/// type permitted to redirect to loopback.
bool googleAnySignInSupported({
  required String serverClientId,
  String desktopClientId = '',
}) =>
    googleSignInSupported(serverClientId) ||
    desktopSignInSupported(desktopClientId);

/// Whether the loopback flow can run here.
///
/// True off the plugin's platforms, where a browser and a bindable socket are
/// what the flow actually needs. False on the plugin's own platforms, which
/// take the better native path, and on web, which can do neither.
bool desktopSignInSupported(String desktopClientId) =>
    !platform_gate.googleSignInSupported &&
    platform_gate.hasLoopbackBrowser &&
    desktopClientId.isNotEmpty;

/// Which sign-in flow this platform should use.
///
/// A value rather than a branch inside the fetcher: the choice is the part
/// worth testing, and returning it lets the suite assert the routing on a
/// host that can run neither flow for real.
enum GoogleFlow {
  /// The `google_sign_in` plugin: Android and iOS.
  plugin,

  /// OAuth loopback in the system browser: Linux, Windows, macOS.
  desktop,

  /// Neither is available; the caller falls back to the password path.
  none,
}

/// Picks the flow for this platform and configuration.
GoogleFlow googleFlowFor({
  required String serverClientId,
  String desktopClientId = '',
}) {
  if (googleSignInSupported(serverClientId)) return GoogleFlow.plugin;
  if (desktopSignInSupported(desktopClientId)) return GoogleFlow.desktop;
  return GoogleFlow.none;
}

/// Returns a Google ID token through whichever flow this platform supports.
///
/// Null when neither is available or the user backs out -- the caller falls
/// back to the password path either way.
Future<String?> googleAnyIdToken({
  required String serverClientId,
  String desktopClientId = '',
}) async {
  switch (googleFlowFor(
    serverClientId: serverClientId,
    desktopClientId: desktopClientId,
  )) {
    // Two one-line delegations, each reaching what `flutter test` cannot: a
    // platform channel and a real browser. The decision above them -- which
    // flow, and whether any runs at all -- is pure and fully covered.
    // coverage:ignore-start
    case GoogleFlow.plugin:
      return googleIdToken(serverClientId: serverClientId);
    case GoogleFlow.desktop:
      return googleDesktopIdToken(clientId: desktopClientId);
    // coverage:ignore-end
    case GoogleFlow.none:
      return null;
  }
}
