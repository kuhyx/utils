import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

/// Pumps a screen with one button that opens the confirmation and records
/// whatever it returned.
Future<List<bool?>> _pumpConfirm(
  WidgetTester tester, {
  String confirmLabel = 'Delete',
  String cancelLabel = 'Cancel',
}) async {
  final results = <bool?>[];
  await tester.pumpWidget(
    MaterialApp(
      theme: buildDarkTheme(),
      home: Scaffold(
        body: Builder(
          builder: (context) => ElevatedButton(
            onPressed: () async {
              results.add(
                await confirmDestructive(
                  context,
                  title: 'Delete note?',
                  message: 'This cannot be undone.',
                  confirmLabel: confirmLabel,
                  cancelLabel: cancelLabel,
                ),
              );
            },
            child: const Text('open'),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
  return results;
}

void main() {
  testWidgets('shows the title and message', (tester) async {
    await _pumpConfirm(tester);
    expect(find.text('Delete note?'), findsOneWidget);
    expect(find.text('This cannot be undone.'), findsOneWidget);
  });

  testWidgets('returns true when the destructive action is chosen', (
    tester,
  ) async {
    final results = await _pumpConfirm(tester);
    await tester.tap(find.text('Delete'));
    await tester.pumpAndSettle();
    expect(results, [true]);
  });

  testWidgets('returns false when cancelled', (tester) async {
    final results = await _pumpConfirm(tester);
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(results, [false]);
  });

  testWidgets('Escape dismisses as a refusal', (tester) async {
    final results = await _pumpConfirm(tester);
    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pumpAndSettle();
    expect(results, [false]);
  });

  testWidgets('a barrier dismissal counts as a refusal, not a null', (
    tester,
  ) async {
    final results = await _pumpConfirm(tester);
    // Tap the barrier, well outside the dialog.
    await tester.tapAt(const Offset(10, 10));
    await tester.pumpAndSettle();
    expect(results, [false]);
  });

  testWidgets('autofocuses Cancel so a reflexive Return is safe', (
    tester,
  ) async {
    final results = await _pumpConfirm(tester);
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(results, [false], reason: 'Return must not delete');
  });

  testWidgets('styles the destructive action with the error color', (
    tester,
  ) async {
    await _pumpConfirm(tester);
    final button = tester.widget<TextButton>(
      find.ancestor(of: find.text('Delete'), matching: find.byType(TextButton)),
    );
    final color = button.style?.foregroundColor?.resolve({});
    expect(color, buildDarkTheme().colorScheme.error);
  });

  testWidgets('honours custom labels', (tester) async {
    final results = await _pumpConfirm(
      tester,
      confirmLabel: 'Discard',
      cancelLabel: 'Keep',
    );
    expect(find.text('Discard'), findsOneWidget);
    await tester.tap(find.text('Keep'));
    await tester.pumpAndSettle();
    expect(results, [false]);
  });
}
