/// Outcome of a Firebase connect attempt, distinguishing why it did or did
/// not end connected -- the UI needs different copy for each case, and
/// collapsing them lost that distinction in the app-local copies this
/// generalizes.
enum FirebaseConnectOutcome {
  /// Signed in and the session is confirmed stored.
  connected,

  /// The client rejected the given account (bad password / wrong account).
  rejected,

  /// The user dismissed the Google picker. Not an error.
  cancelled,

  /// Google signed in, but this device did not end up with a stored
  /// session -- the client came back non-null yet [FirebaseSyncController]
  /// re-reads state rather than trusting that, and found nothing durable.
  signedInButNotPersisted,

  /// Google succeeded but resolved to a uid the security rules do not pin
  /// (wrong account entirely).
  wrongAccount,

  /// Any other failure (network, unreachable keystore, etc).
  failed,
}

/// Result of a [FirebaseSyncController.connectWithPassword] or
/// [FirebaseSyncController.connectWithGoogle] call.
class FirebaseConnectResult {
  /// Creates a [FirebaseConnectResult].
  const FirebaseConnectResult({
    required this.outcome,
    this.email,
    this.message,
  });

  /// What happened.
  final FirebaseConnectOutcome outcome;

  /// The connected account's email, when known.
  final String? email;

  /// Human-readable detail for [FirebaseConnectOutcome.failed] and
  /// [FirebaseConnectOutcome.wrongAccount].
  final String? message;
}
