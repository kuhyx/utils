import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('AppStatusColors.standard', () {
    const colors = AppStatusColors.standard();

    test('uses the frozen status hues', () {
      expect(colors.success, AppPalette.success);
      expect(colors.warning, AppPalette.warning);
      expect(colors.danger, AppPalette.danger);
      expect(colors.info, AppPalette.info);
      expect(colors.onStatus, AppPalette.onFill);
    });
  });

  group('copyWith', () {
    const base = AppStatusColors.standard();

    test('replaces only the named field', () {
      const green = Color(0xFF00FF00);
      final copy = base.copyWith(success: green);
      expect(copy.success, green);
      expect(copy.warning, base.warning);
      expect(copy.danger, base.danger);
      expect(copy.info, base.info);
      expect(copy.onStatus, base.onStatus);
    });

    test('replaces every field when all are given', () {
      const other = AppStatusColors(
        success: Color(0xFF111111),
        warning: Color(0xFF222222),
        danger: Color(0xFF333333),
        info: Color(0xFF444444),
        onStatus: Color(0xFF555555),
      );
      final copy = base.copyWith(
        success: other.success,
        warning: other.warning,
        danger: other.danger,
        info: other.info,
        onStatus: other.onStatus,
      );
      expect(copy.success, other.success);
      expect(copy.warning, other.warning);
      expect(copy.danger, other.danger);
      expect(copy.info, other.info);
      expect(copy.onStatus, other.onStatus);
    });

    test('returns an equivalent set when given nothing', () {
      final copy = base.copyWith();
      expect(copy.success, base.success);
      expect(copy.onStatus, base.onStatus);
    });
  });

  group('lerp', () {
    const base = AppStatusColors.standard();
    const other = AppStatusColors(
      success: Color(0xFF000000),
      warning: Color(0xFF000000),
      danger: Color(0xFF000000),
      info: Color(0xFF000000),
      onStatus: Color(0xFF000000),
    );

    test('returns this when the other set is null', () {
      expect(base.lerp(null, 0.5), same(base));
    });

    test('returns the endpoints at t=0 and t=1', () {
      expect(base.lerp(other, 0).success, base.success);
      expect(base.lerp(other, 1).success, other.success);
    });

    test('interpolates every field', () {
      final mid = base.lerp(other, 0.5);
      expect(mid.success, Color.lerp(base.success, other.success, 0.5));
      expect(mid.warning, Color.lerp(base.warning, other.warning, 0.5));
      expect(mid.danger, Color.lerp(base.danger, other.danger, 0.5));
      expect(mid.info, Color.lerp(base.info, other.info, 0.5));
      expect(mid.onStatus, Color.lerp(base.onStatus, other.onStatus, 0.5));
    });
  });

  group('context.statusColors', () {
    testWidgets('reads the extension off a theme built by buildAppTheme', (
      tester,
    ) async {
      late AppStatusColors found;
      await tester.pumpWidget(
        MaterialApp(
          theme: buildDarkTheme(),
          home: Builder(
            builder: (context) {
              found = context.statusColors;
              return const SizedBox.shrink();
            },
          ),
        ),
      );
      expect(found.success, AppPalette.success);
    });

    testWidgets('falls back to the standard set on a bare theme', (
      tester,
    ) async {
      late AppStatusColors found;
      await tester.pumpWidget(
        MaterialApp(
          theme: ThemeData(),
          home: Builder(
            builder: (context) {
              found = context.statusColors;
              return const SizedBox.shrink();
            },
          ),
        ),
      );
      expect(found.success, AppPalette.success);
      expect(found.danger, AppPalette.danger);
    });
  });
}
