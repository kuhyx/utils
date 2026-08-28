/// Shared "Sync settings" UI: Firebase (primary) and an optional per-app
/// local backup slot.
///
/// This package deliberately never touches `flutter_secure_storage` or
/// `google_sign_in` itself -- every keystore read/write and every platform
/// sign-in call arrives here as an already-built closure, exactly as each
/// app's own `SettingsScreen` already injected them before this package
/// existed. That keeps the controller pure Dart and 100%-coverable without
/// a plugin platform-interface fake, and keeps each app's three-line
/// keystore adapter where it already lived (and was already
/// `// coverage:ignore`d for the same platform-channel reason).
library;

export 'src/backup_slot.dart';
export 'src/firebase_connect_result.dart';
export 'src/firebase_sync_controller.dart';
export 'src/sync_settings_screen.dart';
