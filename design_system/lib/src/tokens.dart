/// The frozen design tokens, as importable Dart instead of a token table
/// every repo transcribes by hand.
///
/// Values are the six-repo consensus (todo, home_inventory, dufs-cloud,
/// habit_stack, workout_app, untools all shipped a byte-identical copy of
/// these scales), which is also exactly what `unified-design-system/tokens.md`
/// specifies. Repos that had drifted are corrected *to* this file, not the
/// other way round.
library;

import 'package:flutter/widgets.dart';

/// The raw palette, as named constants.
///
/// Prefer reading colors off `Theme.of(context).colorScheme` (or
/// [AppStatusColors] for the status hues) — this class exists so the theme
/// builders and the very few places that genuinely need a literal have one
/// shared source, rather than 343 scattered `Color(0x…)` values.
abstract final class AppPalette {
  /// Dark background. Same value as the shared launcher-icon charcoal.
  static const Color ink = Color(0xFF211D1B);

  /// Dark elevated surface, step 1.
  static const Color inkRaised1 = Color(0xFF2B2624);

  /// Dark elevated surface, step 2 (kept within 12% luma of the background).
  static const Color inkRaised2 = Color(0xFF38312E);

  /// Border on dark surfaces.
  static const Color lineDark = Color(0xFF463E3A);

  /// Primary text on dark. Near-white, deliberately not pure white.
  static const Color textOnDark = Color(0xFFECEAE9);

  /// Secondary/caption text on dark.
  static const Color mutedOnDark = Color(0xFFAAA09A);

  /// Light background.
  static const Color paper = Color(0xFFF6F4F3);

  /// Light elevated surface — lighter than the background, per rule 15.
  static const Color paperRaised = Color(0xFFFCFBFB);

  /// Border on light surfaces.
  static const Color lineLight = Color(0xFFE0DAD7);

  /// Primary text on light. Reuses [ink] — a deliberate symmetry.
  static const Color textOnLight = ink;

  /// Secondary/caption text on light.
  static const Color mutedOnLight = Color(0xFF70625B);

  /// The single accent hue. The palette has one accent, not a second
  /// secondary hue.
  static const Color accent = Color(0xFFB8862E);

  /// Informational status — the accent, reused.
  static const Color info = accent;

  /// Success status.
  static const Color success = Color(0xFF8A9A3C);

  /// Warning status.
  static const Color warning = Color(0xFFE0A63C);

  /// Danger/error status.
  static const Color danger = Color(0xFFE2585F);

  /// Text drawn on top of a filled accent/status surface. Dark, not white:
  /// the accent is light enough that white text fails contrast on it.
  static const Color onFill = ink;
}

/// Shared spacing scale (4px base) — round any new value to one of these
/// instead of introducing an off-scale literal.
abstract final class AppSpacing {
  /// 4px.
  static const double xs = 4;

  /// 8px.
  static const double sm = 8;

  /// 16px.
  static const double md = 16;

  /// 24px.
  static const double lg = 24;

  /// 32px.
  static const double xl = 32;

  /// 48px.
  static const double xxl = 48;
}

/// Shared corner-radius scale. Nested radii should be `outer - gap`, not a
/// fixed constant — compute per instance per safe-design-rules rule 24.
abstract final class AppRadius {
  /// Buttons, inputs, chips.
  static const double sm = 8;

  /// Cards.
  static const double md = 12;

  /// Sheets, dialogs.
  static const double lg = 16;
}

/// Shared type scale (px). `body` is the floor for anything a user reads;
/// `label`/`caption` are for UI chrome only (timestamps, badges, tags).
abstract final class AppTextSize {
  /// 12px — chrome only.
  static const double caption = 12;

  /// 14px — chrome only.
  static const double label = 14;

  /// 16px — the floor for actual reading content.
  static const double body = 16;

  /// 20px.
  static const double subtitle = 20;

  /// 24px.
  static const double title = 24;

  /// 32px.
  static const double display = 32;
}

/// Shared motion durations. Frozen in `unified-design-system/motion.md`, which
/// carries the rationale for each step and the reduced-motion contract.
///
/// Under `MediaQuery.of(context).disableAnimations` every value here collapses
/// to [instant]. Haptics and sound are *not* motion and are unaffected by that
/// preference — see `AppHaptic` in `motion.md`'s vocabulary.
abstract final class AppDuration {
  /// 0ms — no animation. The reduced-motion collapse target.
  static const Duration instant = Duration.zero;

  /// 120ms — state on an element already under the cursor/finger: hover,
  /// press, checkbox, ripple. The floor at which motion reads *as* motion.
  static const Duration fast = Duration(milliseconds: 120);

  /// 200ms — the default. Anything entering, leaving or moving within the
  /// current view: toasts, expanding rows, tab switches.
  static const Duration base = Duration(milliseconds: 200);

  /// 320ms — full-surface change: sheets, dialogs, page transitions. The
  /// ceiling; past ~350ms the interface feels like it is waiting on itself.
  static const Duration slow = Duration(milliseconds: 320);
}

/// Shared easing curves, named for what the motion does at its *end* — that is
/// the part the eye actually reads.
///
/// Never use a symmetric `ease-in-out` on an element that enters or exits: it
/// makes an arrival look like it is braking and a departure look reluctant.
abstract final class AppCurve {
  /// Starts and ends on screen. Fast out of the gate, settles gently.
  static const Curve standard = Cubic(0.2, 0, 0, 1);

  /// Entering the screen. Starts at full speed — the element is already in
  /// motion from off-stage — and eases to rest.
  static const Curve decelerate = Cubic(0, 0, 0, 1);

  /// Leaving the screen. Eases in, exits at speed: no settle, because there is
  /// nothing left to settle onto.
  static const Curve accelerate = Cubic(0.3, 0, 1, 1);
}

/// Prose/paragraph line-length cap (rule 21).
///
/// Desktop builds here are Chrome `--app` windows that can be arbitrarily
/// wide (potentially 4K), so rendered/edited body text needs an explicit
/// column width instead of filling the whole viewport.
const double kProseMaxWidth = 640;
