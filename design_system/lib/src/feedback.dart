/// Transient feedback (`SnackBar`) helpers.
///
/// There were ~38 raw `ScaffoldMessenger.of(context).showSnackBar(...)` call
/// sites across the fleet and zero helpers, so every one of them re-decided
/// duration, styling, and whether to clear the previous snack bar. These two
/// functions make that one decision.
library;

import 'package:design_system/src/status_colors.dart';
import 'package:design_system/src/tokens.dart';
import 'package:flutter/material.dart';

/// How long a neutral confirmation stays up.
const Duration _toastDuration = Duration(seconds: 3);

/// How long an error stays up. Longer than a toast: an error the user missed
/// is an error they will hit again.
const Duration _errorDuration = Duration(seconds: 5);

/// Shows a neutral, transient confirmation ("Saved", "Copied").
///
/// Returns null when [context] has no `ScaffoldMessenger` above it — which
/// happens routinely when an async callback completes after its screen was
/// popped, and should not throw.
ScaffoldFeatureController<SnackBar, SnackBarClosedReason>? showToast(
  BuildContext context,
  String message,
) {
  return _show(context, message, background: null, foreground: null);
}

/// Shows a transient error, in the danger hue.
///
/// Use for something that *failed*, not for something merely noteworthy —
/// the color is the signal, so spending it on routine confirmations makes a
/// real failure invisible.
ScaffoldFeatureController<SnackBar, SnackBarClosedReason>? showError(
  BuildContext context,
  String message,
) {
  final colors = context.statusColors;
  return _show(
    context,
    message,
    background: colors.danger,
    foreground: colors.onStatus,
  );
}

ScaffoldFeatureController<SnackBar, SnackBarClosedReason>? _show(
  BuildContext context,
  String message, {
  required Color? background,
  required Color? foreground,
}) {
  final messenger = ScaffoldMessenger.maybeOf(context);
  if (messenger == null) {
    return null;
  }
  // Replace rather than queue: a queued snack bar describes an action the
  // user has already moved on from, and shows up seconds late.
  messenger.clearSnackBars();
  return messenger.showSnackBar(
    SnackBar(
      content: Text(
        message,
        style: foreground == null ? null : TextStyle(color: foreground),
      ),
      backgroundColor: background,
      duration: background == null ? _toastDuration : _errorDuration,
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppRadius.sm),
      ),
    ),
  );
}
