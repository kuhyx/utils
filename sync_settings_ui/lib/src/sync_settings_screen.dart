import 'dart:async';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter/material.dart';
import 'package:sync_settings_ui/src/backup_slot.dart';
import 'package:sync_settings_ui/src/firebase_sync_controller.dart';

part 'sync_settings_sections.dart';
part 'sync_settings_widget.dart';

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
