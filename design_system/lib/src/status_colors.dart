/// Status hues (success/warning/danger/info) as a `ThemeExtension`.
///
/// `ColorScheme` has a slot for `error` but none for success, warning or a
/// separate info hue, which is why five repos each grew their own copy of
/// this. Reading them off the theme — rather than off a raw constant —
/// keeps a widget correct if a surface ever renders under a different
/// brightness than the app default.
library;

import 'package:design_system/src/tokens.dart';
import 'package:flutter/material.dart';

/// The four status colors, plus the text color to draw on top of them.
@immutable
class AppStatusColors extends ThemeExtension<AppStatusColors> {
  /// Creates a status-color set. Prefer [AppStatusColors.standard] unless a
  /// surface genuinely needs different hues.
  const AppStatusColors({
    required this.success,
    required this.warning,
    required this.danger,
    required this.info,
    required this.onStatus,
  });

  /// The frozen palette's status hues. Identical in light and dark: these
  /// are always used as *fills* with [onStatus] text on top, never as text
  /// on the page background, so they do not need a per-brightness variant.
  const AppStatusColors.standard()
    : success = AppPalette.success,
      warning = AppPalette.warning,
      danger = AppPalette.danger,
      info = AppPalette.info,
      onStatus = AppPalette.onFill;

  /// Completed / healthy / within-budget.
  final Color success;

  /// Needs attention but is not yet a failure.
  final Color warning;

  /// Failed, over-budget, or destructive.
  final Color danger;

  /// Neutral emphasis. The accent hue, reused.
  final Color info;

  /// Text/icon color to draw on top of any of the four fills above.
  final Color onStatus;

  @override
  AppStatusColors copyWith({
    Color? success,
    Color? warning,
    Color? danger,
    Color? info,
    Color? onStatus,
  }) {
    return AppStatusColors(
      success: success ?? this.success,
      warning: warning ?? this.warning,
      danger: danger ?? this.danger,
      info: info ?? this.info,
      onStatus: onStatus ?? this.onStatus,
    );
  }

  @override
  AppStatusColors lerp(covariant AppStatusColors? other, double t) {
    if (other == null) {
      return this;
    }
    return AppStatusColors(
      success: Color.lerp(success, other.success, t)!,
      warning: Color.lerp(warning, other.warning, t)!,
      danger: Color.lerp(danger, other.danger, t)!,
      info: Color.lerp(info, other.info, t)!,
      onStatus: Color.lerp(onStatus, other.onStatus, t)!,
    );
  }
}

/// Convenience access to [AppStatusColors] from a `BuildContext`.
extension AppStatusColorsContext on BuildContext {
  /// The status colors for the nearest theme.
  ///
  /// Falls back to [AppStatusColors.standard] when the ambient theme was not
  /// built by `buildAppTheme` — a widget test that pumps a bare
  /// `MaterialApp` should still render, not crash on a null extension.
  AppStatusColors get statusColors =>
      Theme.of(this).extension<AppStatusColors>() ??
      const AppStatusColors.standard();
}
