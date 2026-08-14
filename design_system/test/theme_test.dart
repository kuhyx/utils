import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('buildDarkTheme', () {
    final theme = buildDarkTheme();

    test('uses the frozen dark palette', () {
      final scheme = theme.colorScheme;
      expect(scheme.brightness, Brightness.dark);
      expect(scheme.surface, AppPalette.ink);
      expect(scheme.surfaceContainerHigh, AppPalette.inkRaised1);
      expect(scheme.surfaceContainerHighest, AppPalette.inkRaised2);
      expect(scheme.onSurface, AppPalette.textOnDark);
      expect(scheme.onSurfaceVariant, AppPalette.mutedOnDark);
      expect(scheme.outline, AppPalette.lineDark);
      expect(scheme.error, AppPalette.danger);
    });

    test('scaffold background matches the surface', () {
      expect(theme.scaffoldBackgroundColor, theme.colorScheme.surface);
    });
  });

  group('buildLightTheme', () {
    final theme = buildLightTheme();

    test('uses the frozen light palette', () {
      final scheme = theme.colorScheme;
      expect(scheme.brightness, Brightness.light);
      expect(scheme.surface, AppPalette.paper);
      expect(scheme.surfaceContainerHighest, AppPalette.paperRaised);
      expect(scheme.onSurface, AppPalette.textOnLight);
      expect(scheme.onSurfaceVariant, AppPalette.mutedOnLight);
      expect(scheme.outline, AppPalette.lineLight);
      expect(scheme.error, AppPalette.danger);
    });

    test('scaffold background matches the surface', () {
      expect(theme.scaffoldBackgroundColor, theme.colorScheme.surface);
    });
  });

  for (final entry in {
    'dark': buildDarkTheme(),
    'light': buildLightTheme(),
  }.entries) {
    group('${entry.key} theme', () {
      final theme = entry.value;

      test('is Material 3', () {
        expect(theme.useMaterial3, isTrue);
      });

      test('has one accent: secondary and tertiary mirror primary', () {
        final scheme = theme.colorScheme;
        expect(scheme.primary, AppPalette.accent);
        expect(scheme.secondary, AppPalette.accent);
        expect(scheme.tertiary, AppPalette.accent);
      });

      test('draws dark text on every filled surface', () {
        final scheme = theme.colorScheme;
        expect(scheme.onPrimary, AppPalette.onFill);
        expect(scheme.onSecondary, AppPalette.onFill);
        expect(scheme.onTertiary, AppPalette.onFill);
        expect(scheme.onError, AppPalette.onFill);
      });

      test('never leaks stock Material teal into container slots', () {
        final scheme = theme.colorScheme;
        expect(scheme.onSecondaryContainer, AppPalette.accent);
        expect(scheme.onTertiaryContainer, AppPalette.accent);
        expect(scheme.secondaryContainer, scheme.outline);
        expect(scheme.tertiaryContainer, scheme.outline);
      });

      test('registers the status colors as a theme extension', () {
        final status = theme.extension<AppStatusColors>();
        expect(status, isNotNull);
        expect(status!.success, AppPalette.success);
      });

      test('sizes text from the shared type scale', () {
        final text = theme.textTheme;
        expect(text.bodyLarge?.fontSize, AppTextSize.body);
        expect(text.bodyMedium?.fontSize, AppTextSize.body);
        expect(text.titleLarge?.fontSize, AppTextSize.title);
        expect(text.titleMedium?.fontSize, AppTextSize.subtitle);
        expect(text.labelMedium?.fontSize, AppTextSize.label);
        expect(text.labelSmall?.fontSize, AppTextSize.caption);
      });

      test('inputs are filled, rounded, and show a 2px accent focus ring', () {
        final input = theme.inputDecorationTheme;
        expect(input.filled, isTrue);
        expect(input.fillColor, theme.colorScheme.surfaceContainerHighest);

        final focused = input.focusedBorder! as OutlineInputBorder;
        expect(focused.borderSide.color, AppPalette.accent);
        expect(focused.borderSide.width, 2.0);
        expect(
          focused.borderRadius,
          BorderRadius.circular(AppRadius.sm),
        );

        for (final border in [input.border!, input.enabledBorder!]) {
          expect(
            (border as OutlineInputBorder).borderSide.color,
            theme.colorScheme.outline,
          );
        }
        expect(input.labelStyle?.color, theme.colorScheme.onSurfaceVariant);
      });

      test('dividers use the outline color at 1px', () {
        expect(theme.dividerTheme.color, theme.colorScheme.outline);
        expect(theme.dividerTheme.thickness, 1.0);
        expect(theme.dividerTheme.space, AppSpacing.md);
      });
    });
  }
}
