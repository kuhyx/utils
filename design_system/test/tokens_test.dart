import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('AppSpacing', () {
    test('is a 4px-based scale in ascending order', () {
      const scale = [
        AppSpacing.xs,
        AppSpacing.sm,
        AppSpacing.md,
        AppSpacing.lg,
        AppSpacing.xl,
        AppSpacing.xxl,
      ];
      expect(scale, [4.0, 8.0, 16.0, 24.0, 32.0, 48.0]);
      for (final step in scale) {
        expect(step % 4, 0, reason: '$step is off the 4px grid');
      }
    });
  });

  group('AppRadius', () {
    test('matches the frozen scale', () {
      expect([AppRadius.sm, AppRadius.md, AppRadius.lg], [8.0, 12.0, 16.0]);
    });
  });

  group('AppTextSize', () {
    test('matches the frozen scale', () {
      expect(
        [
          AppTextSize.caption,
          AppTextSize.label,
          AppTextSize.body,
          AppTextSize.subtitle,
          AppTextSize.title,
          AppTextSize.display,
        ],
        [12.0, 14.0, 16.0, 20.0, 24.0, 32.0],
      );
    });

    test('body is the reading floor', () {
      expect(AppTextSize.caption, lessThan(AppTextSize.body));
      expect(AppTextSize.label, lessThan(AppTextSize.body));
    });
  });

  group('AppPalette', () {
    test('matches the frozen token table', () {
      expect(AppPalette.ink, const Color(0xFF211D1B));
      expect(AppPalette.inkRaised1, const Color(0xFF2B2624));
      expect(AppPalette.inkRaised2, const Color(0xFF38312E));
      expect(AppPalette.lineDark, const Color(0xFF463E3A));
      expect(AppPalette.textOnDark, const Color(0xFFECEAE9));
      expect(AppPalette.mutedOnDark, const Color(0xFFAAA09A));
      expect(AppPalette.paper, const Color(0xFFF6F4F3));
      expect(AppPalette.paperRaised, const Color(0xFFFCFBFB));
      expect(AppPalette.lineLight, const Color(0xFFE0DAD7));
      expect(AppPalette.mutedOnLight, const Color(0xFF70625B));
      expect(AppPalette.accent, const Color(0xFFB8862E));
      expect(AppPalette.success, const Color(0xFF8A9A3C));
      expect(AppPalette.warning, const Color(0xFFE0A63C));
      expect(AppPalette.danger, const Color(0xFFE2585F));
    });

    test(
      'reuses ink for text-on-light and on-fill, as the table specifies',
      () {
        expect(AppPalette.textOnLight, AppPalette.ink);
        expect(AppPalette.onFill, AppPalette.ink);
      },
    );

    test('has one accent hue: info mirrors it', () {
      expect(AppPalette.info, AppPalette.accent);
    });
  });

  test('kProseMaxWidth caps line length', () {
    expect(kProseMaxWidth, 640.0);
  });

  group('AppDuration', () {
    test('matches the frozen scale, ascending', () {
      const scale = [
        AppDuration.instant,
        AppDuration.fast,
        AppDuration.base,
        AppDuration.slow,
      ];
      expect(scale.map((d) => d.inMilliseconds), [0, 120, 200, 320]);
      for (var i = 1; i < scale.length; i++) {
        expect(
          scale[i] > scale[i - 1],
          isTrue,
          reason: 'step $i is not longer than the one before it',
        );
      }
    });

    test('instant is the zero the reduced-motion contract collapses to', () {
      expect(AppDuration.instant, Duration.zero);
    });

    test(
      'stays within the perceptible band: nothing over the 320ms ceiling',
      () {
        expect(AppDuration.slow.inMilliseconds, lessThanOrEqualTo(350));
        expect(AppDuration.fast.inMilliseconds, greaterThanOrEqualTo(100));
      },
    );
  });

  group('AppCurve', () {
    const curves = {
      'standard': AppCurve.standard,
      'decelerate': AppCurve.decelerate,
      'accelerate': AppCurve.accelerate,
    };

    test('every curve is anchored at both ends', () {
      curves.forEach((name, curve) {
        expect(curve.transform(0), closeTo(0, 1e-6), reason: '$name at t=0');
        expect(curve.transform(1), closeTo(1, 1e-6), reason: '$name at t=1');
      });
    });

    test('matches the frozen control points', () {
      expect(AppCurve.standard, const Cubic(0.2, 0, 0, 1));
      expect(AppCurve.decelerate, const Cubic(0, 0, 0, 1));
      expect(AppCurve.accelerate, const Cubic(0.3, 0, 1, 1));
    });

    test('decelerate leads and accelerate trails, as their names promise', () {
      // Named for what they do at the END: decelerate has covered most of the
      // distance by the midpoint (it is settling), accelerate has covered
      // little (it is still winding up).
      expect(AppCurve.decelerate.transform(0.5), greaterThan(0.5));
      expect(AppCurve.accelerate.transform(0.5), lessThan(0.5));
    });
  });
}
