/// Compile-time sandbox namespace for the Realtime Database.
///
/// Build a test app with `--dart-define=SYNC_NAMESPACE=sandbox/slot3` and every
/// RTDB path the library reads or writes moves under `/sandbox/slot3/`, so a
/// test build can never touch real data. Sign-in is unchanged (real account).
/// Empty, the default, leaves every path exactly as it was.
library;

import 'firebase_config.dart';

/// The `SYNC_NAMESPACE` dart-define; empty means production paths.
const String syncNamespace = String.fromEnvironment('SYNC_NAMESPACE');

final RegExp _allowed = RegExp(r'^sandbox/[a-z0-9_-]+$');

/// Returns [namespace] when it is empty or `sandbox/<slot>`, else throws.
///
/// Fails closed: a typo must stop the app at startup, never quietly fall back
/// to production paths. A trailing newline is rejected too.
String checkSyncNamespace(String namespace) {
  if (namespace.isEmpty || _allowed.hasMatch(namespace)) return namespace;
  throw ConfigException(
    'SYNC_NAMESPACE "$namespace" is invalid: it must be empty or match '
    r'^sandbox/[a-z0-9_-]+$ (e.g. sandbox/slot3)',
  );
}
