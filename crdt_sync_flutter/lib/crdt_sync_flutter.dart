/// The Flutter half of `crdt_sync`.
///
/// `crdt_sync` is pure Dart so it can run from CLI tools and headless
/// systemd jobs. That leaves every Flutter app to write the same glue:
/// a `flutter_secure_storage` adapter, a persisted device id, an account
/// store, and a client-opening function. Four apps had copied it, and the
/// copies had drifted -- `todo` carried an opt-out flag and a seeded-session
/// path the others never received.
///
/// This package owns that glue. A new app needs a [SyncApp] and one call to
/// [openSync]; see the README.
library;

export 'src/account_store.dart';
export 'src/bootstrap.dart';
export 'src/device_id.dart';
export 'src/keystore.dart';
