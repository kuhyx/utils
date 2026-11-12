/// A text-free control to enter the shared crdt-sync passphrase: a lock icon
/// opens a hidden field; the check icon (or Enter) saves it to the keystore.
library;

import 'package:crdt_sync_flutter/src/e2e_bootstrap.dart';
import 'package:crdt_sync_flutter/src/keystore.dart';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Lock icon button; [locked] picks the closed or open lock glyph.
class E2ePassphraseButton extends StatelessWidget {
  /// Creates the button. [onSaved] runs after the passphrase is stored.
  const E2ePassphraseButton({
    required this.locked,
    this.onSaved,
    this.storage = kSecureStorage,
    super.key,
  });

  /// Whether sync is currently locked (no or wrong passphrase).
  final bool locked;

  /// Called after a passphrase is saved, e.g. to retry the sync.
  final VoidCallback? onSaved;

  /// The keystore; only tests pass another.
  final FlutterSecureStorage storage;

  Future<void> _ask(BuildContext context) async {
    final entered = await showDialog<String>(
      context: context,
      builder: (_) => const _PassphraseDialog(),
    );
    if (entered == null || entered.isEmpty) return;
    await saveE2ePassphrase(entered, storage: storage);
    onSaved?.call();
  }

  @override
  Widget build(BuildContext context) => IconButton(
    icon: Icon(locked ? Icons.lock : Icons.lock_open),
    onPressed: () => _ask(context),
  );
}

class _PassphraseDialog extends StatefulWidget {
  const _PassphraseDialog();

  @override
  State<_PassphraseDialog> createState() => _PassphraseDialogState();
}

class _PassphraseDialogState extends State<_PassphraseDialog> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    content: TextField(
      controller: _controller,
      obscureText: true,
      autofocus: true,
      onSubmitted: (value) => Navigator.of(context).pop(value),
    ),
    actions: [
      IconButton(
        icon: const Icon(Icons.check),
        onPressed: () => Navigator.of(context).pop(_controller.text),
      ),
    ],
  );
}
