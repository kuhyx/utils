/// The shared `ThemeData` builders.
///
/// Built from explicit `ColorScheme`s, never `ColorScheme.fromSeed`: the
/// shared palette is hand-picked to hit specific contrast ratios, and a seeded
/// scheme silently replaces those values with algorithmically derived ones.
library;

import 'package:design_system/src/status_colors.dart';
import 'package:design_system/src/tokens.dart';
import 'package:flutter/material.dart';

/// Builds the shared light [ThemeData].
ThemeData buildLightTheme() {
  const colorScheme = ColorScheme.light(
    surface: AppPalette.paper,
    surfaceContainerHighest: AppPalette.paperRaised,
    onSurface: AppPalette.textOnLight,
    onSurfaceVariant: AppPalette.mutedOnLight,
    outline: AppPalette.lineLight,
    primary: AppPalette.accent,
    // Filled surfaces use dark text: the accent is light enough that white
    // on it fails contrast.
    onPrimary: AppPalette.onFill,
    // secondary/tertiary — the shared palette has one accent, not a
    // separate secondary hue, so these mirror primary. Without an explicit
    // value here, widgets that reach for secondaryContainer (e.g.
    // SegmentedButton's selected segment) silently fall back to Flutter's
    // stock Material teal — confirmed live on-device, not just in theory.
    secondary: AppPalette.accent,
    onSecondary: AppPalette.onFill,
    secondaryContainer: AppPalette.lineLight,
    onSecondaryContainer: AppPalette.accent,
    tertiary: AppPalette.accent,
    onTertiary: AppPalette.onFill,
    tertiaryContainer: AppPalette.lineLight,
    onTertiaryContainer: AppPalette.accent,
    error: AppPalette.danger,
    onError: AppPalette.onFill,
  );
  return _buildTheme(colorScheme);
}

/// Builds the shared dark [ThemeData].
ThemeData buildDarkTheme() {
  const colorScheme = ColorScheme.dark(
    surface: AppPalette.ink,
    surfaceContainerHighest: AppPalette.inkRaised2,
    surfaceContainerHigh: AppPalette.inkRaised1,
    onSurface: AppPalette.textOnDark,
    onSurfaceVariant: AppPalette.mutedOnDark,
    outline: AppPalette.lineDark,
    primary: AppPalette.accent,
    onPrimary: AppPalette.onFill,
    secondary: AppPalette.accent,
    onSecondary: AppPalette.onFill,
    secondaryContainer: AppPalette.lineDark,
    onSecondaryContainer: AppPalette.accent,
    tertiary: AppPalette.accent,
    onTertiary: AppPalette.onFill,
    tertiaryContainer: AppPalette.lineDark,
    onTertiaryContainer: AppPalette.accent,
    error: AppPalette.danger,
    onError: AppPalette.onFill,
  );
  return _buildTheme(colorScheme);
}

ThemeData _buildTheme(ColorScheme colorScheme) {
  return ThemeData(
    useMaterial3: true,
    colorScheme: colorScheme,
    scaffoldBackgroundColor: colorScheme.surface,
    extensions: const [AppStatusColors.standard()],
    textTheme: const TextTheme(
      bodyLarge: TextStyle(fontSize: AppTextSize.body),
      bodyMedium: TextStyle(fontSize: AppTextSize.body),
      titleLarge: TextStyle(fontSize: AppTextSize.title),
      titleMedium: TextStyle(fontSize: AppTextSize.subtitle),
      labelMedium: TextStyle(fontSize: AppTextSize.label),
      labelSmall: TextStyle(fontSize: AppTextSize.caption),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: colorScheme.surfaceContainerHighest,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppRadius.sm),
        borderSide: BorderSide(color: colorScheme.outline),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppRadius.sm),
        borderSide: BorderSide(color: colorScheme.outline),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(AppRadius.sm),
        borderSide: BorderSide(color: colorScheme.primary, width: 2),
      ),
      labelStyle: TextStyle(color: colorScheme.onSurfaceVariant),
    ),
    dividerTheme: DividerThemeData(
      color: colorScheme.outline,
      thickness: 1,
      space: AppSpacing.md,
    ),
  );
}
