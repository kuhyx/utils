part of 'sync_settings_screen.dart';

/// The two sections the screen composes.
///
/// Split from sync_settings_screen.dart for the 250-line cap;
/// a `part` rather than an import because both sections are
/// library-private and could not be imported at all.
class _FirebaseSection extends StatelessWidget {
  const new({
    required this.connected,
    required this.busy,
    required this.googleAvailable,
    required this.googleUnavailableReason,
    required this.emailController,
    required this.passwordController,
    required this.onConnectPassword,
    required this.onConnectGoogle,
    required this.onDisconnect,
  });

  final bool connected;
  final bool busy;
  final bool googleAvailable;
  final String? googleUnavailableReason;
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
          IconButton(
            onPressed: busy ? null : onDisconnect,
            icon: const Icon(Icons.link_off, semanticLabel: 'Disconnect'),
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
            child: FilledButton(
              onPressed: busy ? null : onConnectGoogle,
              child: const Icon(
                Icons.account_circle,
                semanticLabel: 'Sign in with Google',
              ),
            ),
          ),
          const SizedBox(height: 12),
        ] else if (googleUnavailableReason != null) ...[
          // Disabled, not hidden. A null onPressed cannot be tapped, so this
          // is not the "control that can never succeed" trap -- that one
          // looks live and reports a fake cancellation. This one says why,
          // which beats a screen that silently offers less on one platform.
          // The why is a block glyph beside it, the reason spoken only.
          Row(
            children: [
              const FilledButton(
                onPressed: null,
                child: Icon(
                  Icons.account_circle,
                  semanticLabel: 'Sign in with Google',
                ),
              ),
              const SizedBox(width: 8),
              Icon(
                Icons.block,
                color: Theme.of(context).colorScheme.error,
                semanticLabel: googleUnavailableReason,
              ),
            ],
          ),
          const SizedBox(height: 12),
        ],
        ExpansionTile(
          initiallyExpanded: !googleAvailable,
          title: const Align(
            alignment: Alignment.centerLeft,
            child: Icon(
              Icons.password,
              semanticLabel: 'Use the account password instead',
            ),
          ),
          tilePadding: EdgeInsets.zero,
          childrenPadding: const EdgeInsets.only(bottom: 8),
          children: [
            TextField(
              controller: emailController,
              keyboardType: TextInputType.emailAddress,
              autocorrect: false,
              decoration: const InputDecoration(
                prefixIcon: Icon(
                  Icons.alternate_email,
                  semanticLabel: 'Sync account email',
                ),
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: passwordController,
              obscureText: true,
              autocorrect: false,
              decoration: const InputDecoration(
                prefixIcon: Icon(
                  Icons.lock_outline,
                  semanticLabel: 'Sync account password',
                ),
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: 12),
            Align(
              alignment: Alignment.centerLeft,
              child: FilledButton(
                onPressed: busy ? null : onConnectPassword,
                child: const Icon(
                  Icons.cloud_done,
                  semanticLabel: 'Connect Firebase',
                ),
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _BackupSection extends StatelessWidget {
  const new({
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
          child: OutlinedButton(
            onPressed: onExport,
            child: Icon(Icons.upload, semanticLabel: 'Export ${backup.label}'),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: OutlinedButton(
            onPressed: onImport,
            child: Icon(
              Icons.download,
              semanticLabel: 'Import ${backup.label}',
            ),
          ),
        ),
      ],
    );
  }
}
