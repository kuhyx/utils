import 'package:design_system/design_system.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

/// The bundle key flutter_svg loads for [loader] (see SvgAssetLoader).
String _keyOf(SvgAssetLoader loader) => loader.packageName == null
    ? loader.assetName
    : 'packages/${loader.packageName}/${loader.assetName}';

void main() {
  testWidgets('KLogo loads an asset that is in the bundle', (tester) async {
    await tester.pumpWidget(const Center(child: KLogo()));
    final picture = tester.widget<SvgPicture>(find.byType(SvgPicture));
    final key = _keyOf(picture.bytesLoader as SvgAssetLoader);
    final data = await rootBundle.load(key);
    expect(data.lengthInBytes, greaterThan(0));
  });

  testWidgets('size presets are 24, 32, 48, 96', (tester) async {
    final presets = <(Widget, double)>[
      (const KLogoSmall(), 24),
      (const KLogoMedium(), 32),
      (const KLogoLarge(), 48),
      (const KLogoXLarge(), 96),
    ];
    for (final (logo, side) in presets) {
      await tester.pumpWidget(Center(child: logo));
      expect(tester.getSize(find.byType(SvgPicture)), Size.square(side));
    }
  });

  testWidgets('carries a semantics label', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: KLogo()));
    expect(find.bySemanticsLabel('kuhy logo'), findsOneWidget);
  });

  testWidgets('a color tints the glyphs, none keeps the SVG colours', (
    tester,
  ) async {
    await tester.pumpWidget(
      const Center(child: KLogo(color: Color(0xFFB8862E))),
    );
    expect(
      tester.widget<SvgPicture>(find.byType(SvgPicture)).colorFilter,
      const ColorFilter.mode(Color(0xFFB8862E), BlendMode.srcIn),
    );
    await tester.pumpWidget(const Center(child: KLogo()));
    expect(
      tester.widget<SvgPicture>(find.byType(SvgPicture)).colorFilter,
      isNull,
    );
  });
}
