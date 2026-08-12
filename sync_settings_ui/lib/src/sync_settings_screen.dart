import 'dart:async';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter/material.dart';
import 'package:sync_settings_ui/src/backup_slot.dart';
import 'package:sync_settings_ui/src/firebase_sync_controller.dart';

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

  /// Optional local export/import section. Null omits the "Backup" section
  /// entirely (diet_guard, wake_alarm have no local backup format).
  final BackupSlot? backup;

  @override
  State<SyncSettingsScreen> createState() => _SyncSettingsScreenState();
}

class _SyncSettingsScreenState extends State<SyncSettingsScreen> {
  late final FirebaseSyncController _firebase = FirebaseSyncController(
    accountLoader: widget.accountLoader,
    accountSaver: widget.accountSaver,
    accountClearer: widget.accountClearer,
    sessionProbe: widget.sessionProbe,
    firebaseFactory: widget.firebaseFactory,
    googleFirebaseFactory: widget.googleFirebaseFactory,
  );

  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();

  bool _loading = true;
  bool _firebaseConnected = false;
  bool _busy = false;
  String? _status;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    final status = await _firebase.loadStatus();
    if (!mounted) return;
    setState(() {
      _firebaseConnected = status.connected;
      _emailController.text = status.email ?? '';
      _loading = false;
    });
  }

  // supportsGoogle gates on the factory being non-null; widget.googleAvailable
  // can only narrow further (e.g. a test host reporting the plugin
  // unsupported), never widen. Without the `&&`, `googleAvailable: true`
  // with no googleFirebaseFactory renders a live button whose tap hits
  // FirebaseSyncController's StateError -- a visible control that can never
  // succeed, which is exactly what this gate exists to prevent.
  bool get _googleAvailable =>
      _firebase.supportsGoogle && (widget.googleAvailable ?? true);

  Future<void> _connectFirebase() async {
    final email = _emailController.text.trim();
    final password = _passwordController.text;
    if (email.isEmpty || password.isEmpty) {
      setState(() => _status = 'Enter the sync account email and password.');
      return;
    }
    setState(() {
      _busy = true;
      _status = 'Signing in…';
    });
    final result = await _firebase.connectWithPassword(
      email: email,
      password: password,
    );
    if (!mounted) return;
    _applyConnectResult(result, clearPasswordOnSuccess: true);
  }

  Future<void> _connectGoogle() async {
    setState(() {
      _busy = true;
      _status = 'Signing in…';
    });
    final result = await _firebase.connectWithGoogle();
    if (!mounted) return;
    _applyConnectResult(result, clearPasswordOnSuccess: false);
  }

  void _applyConnectResult(
    FirebaseConnectResult result, {
    required bool clearPasswordOnSuccess,
  }) {
    if (result.email != null) _emailController.text = result.email!;
    if (result.outcome == FirebaseConnectOutcome.connected &&
        clearPasswordOnSuccess) {
      _passwordController.clear();
    }
    setState(() {
      _busy = false;
      _firebaseConnected = result.outcome == FirebaseConnectOutcome.connected;
      _status = switch (result.outcome) {
        FirebaseConnectOutcome.connected => 'Connected to Firebase.',
        FirebaseConnectOutcome.rejected => 'Firebase rejected that account.',
        FirebaseConnectOutcome.cancelled => 'Google sign-in was cancelled.',
        FirebaseConnectOutcome.signedInButNotPersisted =>
          'Signed in, but this device did not save the session - it will '
              'sync over GitHub after a restart. Try connecting again.',
        FirebaseConnectOutcome.wrongAccount => result.message,
        FirebaseConnectOutcome.failed =>
          'Google sign-in failed: ${result.message}',
      };
    });
  }

  Future<void> _disconnectFirebase() async {
    await _firebase.disconnect();
    if (!mounted) return;
    _emailController.clear();
    _passwordController.clear();
    setState(() {
      _firebaseConnected = false;
      _status = 'Firebase disconnected.';
    });
  }

  Future<void> _exportBackup(BackupSlot backup) async {
    try {
      await backup.export();
      if (mounted) setState(() => _status = 'Exported ${backup.label}.');
    } on Exception catch (error) {
      if (mounted) setState(() => _status = 'Export failed: $error');
    }
  }

  Future<void> _importBackup(BackupSlot backup) async {
    try {
      await backup.import();
      if (mounted) setState(() => _status = 'Imported ${backup.label}.');
    } on Exception catch (error) {
      if (mounted) setState(() => _status = 'Import failed: $error');
    }
  }

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return Scaffold(
        appBar: AppBar(title: const Text('Sync settings')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }
    final backup = widget.backup;
    final textTheme = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Sync settings')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('Firebase sync', style: textTheme.titleMedium),
          const SizedBox(height: 8),
          _FirebaseSection(
            connected: _firebaseConnected,
            busy: _busy,
            googleAvailable: _googleAvailable,
            emailController: _emailController,
            passwordController: _passwordController,
            onConnectPassword: _connectFirebase,
            onConnectGoogle: _connectGoogle,
            onDisconnect: _disconnectFirebase,
          ),
          if (backup != null) ...[
            const SizedBox(height: 24),
            const Divider(),
            const SizedBox(height: 8),
            Text('Backup', style: textTheme.titleMedium),
            const SizedBox(height: 8),
            _BackupSection(
              backup: backup,
              onExport: () => _exportBackup(backup),
              onImport: () => _importBackup(backup),
            ),
          ],
          if (_status != null) ...[
            const SizedBox(height: 16),
            Text(_status!, style: textTheme.bodyMedium),
          ],
        ],
      ),
    );
  }
}

class _FirebaseSection extends StatelessWidget {
  const _FirebaseSection({
    required this.connected,
    required this.busy,
    required this.googleAvailable,
    required this.emailController,
    required this.passwordController,
    required this.onConnectPassword,
    required this.onConnectGoogle,
    required this.onDisconnect,
  });

  final bool connected;
  final bool busy;
  final bool googleAvailable;
  final TextEditingController emailController;
  final TextEditingController passwordController;
  final VoidCallback onConnectPassword;
  final VoidCallback onConnectGoogle;
  final VoidCallback onDisconnect;

  @override
  Widget build(BuildContext context) {
    if (connected) {
      return Row(
        children: [
          const Icon(Icons.cloud_done, size: 20),
          const SizedBox(width: 8),
          Expanded(child: Text(emailController.text)),
          TextButton(
            onPressed: busy ? null : onDisconnect,
            child: const Text('Disconnect'),
          ),
        ],
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (googleAvailable) ...[
          Align(
            alignment: Alignment.centerLeft,
            child: FilledButton.icon(
              onPressed: busy ? null : onConnectGoogle,
              icon: const Icon(Icons.account_circle),
              label: const Text('Sign in with Google'),
            ),
          ),
          const SizedBox(height: 12),
        ],
        ExpansionTile(
          initiallyExpanded: !googleAvailable,
          title: const Text('Use the account password instead'),
          tilePadding: EdgeInsets.zero,
          childrenPadding: const EdgeInsets.only(bottom: 8),
          children: [
            TextField(
              controller: emailController,
              keyboardType: TextInputType.emailAddress,
              autocorrect: false,
              decoration: const InputDecoration(
                labelText: 'Sync account email',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: passwordController,
              obscureText: true,
              autocorrect: false,
              decoration: const InputDecoration(
                labelText: 'Sync account password',
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            Align(
              alignment: Alignment.centerLeft,
              child: FilledButton.icon(
                onPressed: busy ? null : onConnectPassword,
                icon: const Icon(Icons.cloud_done),
                label: const Text('Connect Firebase'),
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _BackupSection extends StatelessWidget {
  const _BackupSection({
    required this.backup,
    required this.onExport,
    required this.onImport,
  });

  final BackupSlot backup;
  final VoidCallback onExport;
  final VoidCallback onImport;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: OutlinedButton.icon(
            onPressed: onExport,
            icon: const Icon(Icons.upload),
            label: Text('Export ${backup.label}'),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: OutlinedButton.icon(
            onPressed: onImport,
            icon: const Icon(Icons.download),
            label: Text('Import ${backup.label}'),
          ),
        ),
      ],
    );
  }
}
