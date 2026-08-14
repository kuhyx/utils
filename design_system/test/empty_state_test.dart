import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Built at runtime rather than inlined as a literal, so the `EmptyState`
/// below cannot be const-folded: a const invocation is evaluated at compile
/// time, so the constructor never executes and coverage silently drops.
/// Real call sites interpolate runtime state into these strings anyway.
String _message(int count) => 'Add your first item to get started ($count).';

Future<void> _pumpEmptyState(WidgetTester tester) {
  return tester.pumpWidget(
    MaterialApp(
      theme: buildDarkTheme(),
      home: Scaffold(
        body: EmptyState(
          icon: Icons.inbox_outlined,
          title: 'Nothing here yet',
          message: _message(0),
        ),
      ),
    ),
  );
}

void main() {
  testWidgets('shows the icon, title and message', (tester) async {
    await _pumpEmptyState(tester);
    expect(find.byIcon(Icons.inbox_outlined), findsOneWidget);
    expect(find.text('Nothing here yet'), findsOneWidget);
    expect(find.text(_message(0)), findsOneWidget);
  });

  testWidgets('draws the icon at the shared size in the muted color', (
    tester,
  ) async {
    await _pumpEmptyState(tester);
    final icon = tester.widget<Icon>(find.byType(Icon));
    expect(icon.size, AppSpacing.xxl);
    expect(icon.color, buildDarkTheme().colorScheme.onSurfaceVariant);
  });

  testWidgets('mutes the message but not the title', (tester) async {
    await _pumpEmptyState(tester);
    final scheme = buildDarkTheme().colorScheme;

    final message = tester.widget<Text>(
      find.text(_message(0)),
    );
    expect(message.style?.color, scheme.onSurfaceVariant);
    expect(message.textAlign, TextAlign.center);

    final title = tester.widget<Text>(find.text('Nothing here yet'));
    expect(title.style?.color, isNot(scheme.onSurfaceVariant));
  });

  testWidgets('is a pure placeholder with no action', (tester) async {
    // Deliberate: no donor had an action slot, so adding one would be
    // speculative surface on a widget that has no consumer yet.
    await _pumpEmptyState(tester);
    expect(find.byType(ButtonStyleButton), findsNothing);
  });

  testWidgets('stays centred and shrink-wrapped', (tester) async {
    await _pumpEmptyState(tester);
    expect(find.byType(Center), findsWidgets);
    final column = tester.widget<Column>(find.byType(Column));
    expect(column.mainAxisSize, MainAxisSize.min);
  });
}
