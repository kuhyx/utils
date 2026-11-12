import 'dart:async';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:material_ui/material_ui.dart';
import 'package:sync_settings_ui/src/backup_slot.dart';
import 'package:sync_settings_ui/src/firebase_connect_result.dart';
import 'package:sync_settings_ui/src/firebase_sync_controller.dart';

part 'sync_settings_cues.dart';
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
  _Cue? _status;

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
      setState(
        () => _status = const _Cue.error(
          Icons.edit_off,
          'Enter the sync account email and password.',
        ),
      );
      return;
    }
    setState(() => _busy = true);
    final result = await _firebase.connectWithPassword(
      email: email,
      password: password,
      onProgress: (stage) {
        if (mounted) setState(() => _status = _Cue(Icons.hourglass_top, stage));
      },
    );
    if (!mounted) return;
    _applyConnectResult(result, clearPasswordOnSuccess: true);
  }

  Future<void> _connectGoogle() async {
    setState(() {
      _busy = true;
      _status = const _Cue(Icons.hourglass_top, 'Signing in…');
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
      // One glyph per outcome; the sentence is spoken only.
      _status = switch (result.outcome) {
        FirebaseConnectOutcome.connected => const _Cue(
          Icons.cloud_done,
          'Connected to Firebase.',
        ),
        FirebaseConnectOutcome.rejected => _Cue.error(
          Icons.lock,
          result.message != null
              ? 'Firebase rejected that account: ${result.message}'
              : 'Firebase rejected that account.',
        ),
        FirebaseConnectOutcome.cancelled => const _Cue(
          Icons.cancel_outlined,
          'Google sign-in was cancelled.',
        ),
        FirebaseConnectOutcome.signedInButNotPersisted => const _Cue.error(
          Icons.save_as_outlined,
          'Signed in, but this device did not save the session - it will '
          'sync over GitHub after a restart. Try connecting again.',
        ),
        FirebaseConnectOutcome.wrongAccount => _Cue.error(
          Icons.no_accounts,
          result.message ?? '',
        ),
        FirebaseConnectOutcome.failed => _Cue.error(
          Icons.error,
          'Sign-in failed: ${result.message}',
        ),
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
      _status = const _Cue(Icons.link_off, 'Firebase disconnected.');
    });
  }

  Future<void> _exportBackup(BackupSlot backup) async {
    try {
      await backup.export();
      _show(_Cue(Icons.upload, 'Exported ${backup.label}.'));
    } on BackupCancelled {
      _show(null);
    } on Exception catch (error) {
      _show(_Cue.error(Icons.upload, 'Export failed: $error'));
    }
  }

  Future<void> _importBackup(BackupSlot backup) async {
    try {
      await backup.import();
      _show(_Cue(Icons.download, 'Imported ${backup.label}.'));
    } on BackupCancelled {
      _show(null);
    } on Exception catch (error) {
      _show(_Cue.error(Icons.download, 'Import failed: $error'));
    }
  }

  /// Shows [cue] as the latest result (null clears it), if still mounted.
  void _show(_Cue? cue) {
    if (mounted) setState(() => _status = cue);
  }

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Glyphs in place of the title and section headings (kuhy's textgate
    // rule: nothing he sees carries app-written words); the old words are
    // the spoken labels.
    const title = Icon(Icons.sync, semanticLabel: 'Sync settings');
    if (_loading) {
      return Scaffold(
        appBar: AppBar(title: title),
        body: const Center(child: CircularProgressIndicator()),
      );
    }
    final backup = widget.backup;
    return Scaffold(
      appBar: AppBar(title: title),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const _Heading(Icons.local_fire_department, 'Firebase sync'),
          const SizedBox(height: 8),
          _FirebaseSection(
            connected: _firebaseConnected,
            busy: _busy,
            googleAvailable: _googleAvailable,
            googleUnavailableReason: widget.googleUnavailableReason,
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
            const _Heading(Icons.backup_outlined, 'Backup'),
            const SizedBox(height: 8),
            _BackupSection(
              backup: backup,
              onExport: () => _exportBackup(backup),
              onImport: () => _importBackup(backup),
            ),
          ],
          if (_status case final status?) ...[
            const SizedBox(height: 16),
            _CueView(status),
          ],
        ],
      ),
    );
  }
}
