import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

Future<void> _pumpEmptyState(WidgetTester tester, {Widget? action}) {
  return tester.pumpWidget(
    MaterialApp(
      theme: buildDarkTheme(),
      home: Scaffold(
        body: EmptyState(
          icon: Icons.inbox_outlined,
          title: 'Nothing here yet',
          message: 'Add your first item to get started.',
          action: action,
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
    expect(find.text('Add your first item to get started.'), findsOneWidget);
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
      find.text('Add your first item to get started.'),
    );
    expect(message.style?.color, scheme.onSurfaceVariant);
    expect(message.textAlign, TextAlign.center);

    final title = tester.widget<Text>(find.text('Nothing here yet'));
    expect(title.style?.color, isNot(scheme.onSurfaceVariant));
  });

  testWidgets('omits the action slot by default', (tester) async {
    await _pumpEmptyState(tester);
    expect(find.byType(ElevatedButton), findsNothing);
  });

  testWidgets('renders an action when one is given', (tester) async {
    await _pumpEmptyState(
      tester,
      action: ElevatedButton(onPressed: () {}, child: const Text('Add item')),
    );
    expect(find.text('Add item'), findsOneWidget);
  });

  testWidgets('stays centred and shrink-wrapped', (tester) async {
    await _pumpEmptyState(tester);
    expect(find.byType(Center), findsWidgets);
    final column = tester.widget<Column>(find.byType(Column));
    expect(column.mainAxisSize, MainAxisSize.min);
  });
}
