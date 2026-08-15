/// The GitHub device-flow dialog: shows the user code, opens the page, and
/// polls until the grant is approved.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:github_device_auth/src/device_auth.dart';
import 'package:url_launcher/url_launcher.dart';

/// Dialog shown during the device flow: displays the user code, opens the
/// verification page, and polls until authorized — popping the token (or
/// null if cancelled / failed).
class DeviceCodeDialog extends StatefulWidget {
  /// Creates the dialog for a pending device-flow grant.
  const DeviceCodeDialog({
    required this.device,
    required this.auth,
    super.key,
  });

  /// The pending grant: user code, verification URL, poll interval.
  final DeviceCodeResponse device;

  /// Auth client used to poll for the approved token.
  final GitHubDeviceAuth auth;

  @override
  State<DeviceCodeDialog> createState() => _DeviceCodeDialogState();
}

class _DeviceCodeDialogState extends State<DeviceCodeDialog> {
  String? _error;

  @override
  void initState() {
    super.initState();
    unawaited(_poll());
  }

  Future<void> _poll() async {
    try {
      final token = await widget.auth.pollForToken(widget.device);
      if (mounted) Navigator.of(context).pop(token);
    }
    // `on Object`, not `on Exception`: an `Error` (notably `ArgumentError`
    // from URI parsing) is not an `Exception`, so `on Exception` lets it
    // escape and the dialog spins on "Waiting for authorization…" forever
    // with nothing shown to the user. The same trap silently killed the
    // Firebase sync tick in these apps -- see the 2026-08-11 fix.
    on Object catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  Future<void> _openPage() async {
    await Clipboard.setData(ClipboardData(text: widget.device.userCode));
    await launchUrl(
      Uri.parse(widget.device.verificationUri),
      mode: LaunchMode.externalApplication,
    );
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Authorize on GitHub'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Enter this code on GitHub:'),
          const SizedBox(height: 8),
          SelectableText(
            widget.device.userCode,
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          const SizedBox(height: 16),
          if (_error == null)
            const Row(
              children: [
                SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
                SizedBox(width: 12),
                Expanded(child: Text('Waiting for authorization…')),
              ],
            )
          else
            Text(
              _error!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        FilledButton.icon(
          onPressed: _openPage,
          icon: const Icon(Icons.open_in_new),
          label: const Text('Open GitHub & copy code'),
        ),
      ],
    );
  }
}
