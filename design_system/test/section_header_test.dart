import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Future<void> _pumpHeader(
  WidgetTester tester, {
  Widget? action,
  EdgeInsetsGeometry? padding,
}) {
  return tester.pumpWidget(
    MaterialApp(
      theme: buildDarkTheme(),
      home: Scaffold(
        body: SectionHeader('Filters', action: action, padding: padding),
      ),
    ),
  );
}

void main() {
  testWidgets('shows the title at titleMedium', (tester) async {
    await _pumpHeader(tester);
    expect(find.text('Filters'), findsOneWidget);
    // Compare the resolved size, not the whole TextStyle: the localization
    // delegate merges geometry (weight, letter spacing, line height) into
    // the theme's style before it reaches the widget, so the two objects are
    // never `==` even when the widget is doing exactly the right thing.
    final text = tester.widget<Text>(find.text('Filters'));
    expect(text.style?.fontSize, AppTextSize.subtitle);
    expect(
      text.style?.fontSize,
      buildDarkTheme().textTheme.titleMedium?.fontSize,
    );
  });

  testWidgets('has no padding of its own by default', (tester) async {
    await _pumpHeader(tester);
    expect(
      find.descendant(
        of: find.byType(SectionHeader),
        matching: find.byType(Padding),
      ),
      findsNothing,
    );
  });

  testWidgets('applies padding when asked', (tester) async {
    await _pumpHeader(tester, padding: SectionHeader.defaultPadding);
    final padding = tester.widget<Padding>(
      find
          .descendant(
            of: find.byType(SectionHeader),
            matching: find.byType(Padding),
          )
          .first,
    );
    expect(padding.padding, SectionHeader.defaultPadding);
  });

  testWidgets('omits the action slot by default', (tester) async {
    await _pumpHeader(tester);
    expect(find.byType(IconButton), findsNothing);
  });

  testWidgets('renders a trailing action beside the title', (tester) async {
    await _pumpHeader(
      tester,
      action: IconButton(onPressed: () {}, icon: const Icon(Icons.add)),
    );
    expect(find.byIcon(Icons.add), findsOneWidget);
    // The action sits to the right of the title, not below it.
    final titleRight = tester.getTopRight(find.text('Filters')).dx;
    final actionLeft = tester.getTopLeft(find.byIcon(Icons.add)).dx;
    expect(actionLeft, greaterThanOrEqualTo(titleRight));
  });

  test('defaultPadding groups the title with the content below it', () {
    // Tighter below than above, so the header reads as belonging to the
    // section it labels rather than floating between two of them.
    expect(SectionHeader.defaultPadding.bottom, AppSpacing.xs);
    expect(SectionHeader.defaultPadding.top, AppSpacing.md);
    expect(SectionHeader.defaultPadding.left, AppSpacing.md);
    expect(SectionHeader.defaultPadding.right, AppSpacing.md);
  });
}
