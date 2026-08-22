part of 'sync_settings_screen.dart';

/// The shared "Sync settings" screen: Firebase sync (primary, shown by
/// default) and an optional local backup section.
///
/// Generalized from the near-identical settings screens duplicated across
/// the todo app, diet_guard_app, workout_app, wake_alarm/phone_app and
/// home_inventory. Only the sync-related fields migrate here -- app-specific
/// settings (kcal goals, exercise thresholds, notifications, the
/// battery-exemption toggle) stay behind in each app's own Settings screen,
/// reached via a `ListTile` link to this one.
class SyncSettingsScreen extends StatefulWidget {
  /// Creates a [SyncSettingsScreen].
  const SyncSettingsScreen({
    required this.accountLoader,
    required this.accountSaver,
    required this.accountClearer,
    required this.sessionProbe,
    required this.firebaseFactory,
    this.googleFirebaseFactory,
    this.googleAvailable,
    this.googleUnavailableReason,
    this.backup,
    super.key,
  });

  /// Reads the stored Firebase account. Injected because the keystore is a
  /// platform channel `flutter test` has no binding for.
  final Future<FirebaseAccount?> Function() accountLoader;

  /// Persists the account. See [accountLoader].
  final Future<void> Function(FirebaseAccount) accountSaver;

  /// Forgets the account and any cached session. See [accountLoader].
  final Future<void> Function() accountClearer;

  /// Whether a Firebase session is stored.
  ///
  /// Separate from [accountLoader] because the two answer different
  /// questions: the account marker is bookkeeping, the session is the
  /// credential. A device can hold the second without the first, and
  /// reporting only the first is what made a syncing phone read as
  /// "not connected".
  final Future<bool> Function() sessionProbe;

  /// Builds the Firebase backend from the stored account. Injected so tests
  /// can supply a fake.
  final Future<FirebaseRestClient?> Function() firebaseFactory;

  /// Builds the Firebase backend via Google sign-in. Separate from
  /// [firebaseFactory] because it reaches the Google plugin's platform
  /// channel. Null hides the "Sign in with Google" button entirely.
  final Future<FirebaseRestClient?> Function()? googleFirebaseFactory;

  /// Narrows whether to offer the Google button. Can only turn it off, never
  /// on: the button always requires a non-null [googleFirebaseFactory]
  /// regardless of this value, so a host that sets this true without also
  /// wiring the factory does not get a button that can never succeed. Tests
  /// pass `false` to model a platform that reports Google sign-in
  /// unsupported even though a factory is wired.
  final bool? googleAvailable;

  /// Why Google sign-in is unavailable here, shown under a *disabled* button.
  ///
  /// Null hides the button entirely, which stays the default. Supplying a
  /// reason trades a silently-absent control for one that explains itself --
  /// worth it where a platform genuinely cannot support the flow, and where
  /// its absence would otherwise read as a bug.
  ///
  /// Not the same as a button that can never succeed: this one cannot be
  /// tapped at all, so it can never report a misleading "cancelled".
  final String? googleUnavailableReason;

  /// Optional local export/import section. Null omits the "Backup" section
  /// entirely (diet_guard, wake_alarm have no local backup format).
  final BackupSlot? backup;

  @override
  State<SyncSettingsScreen> createState() => _SyncSettingsScreenState();
}
