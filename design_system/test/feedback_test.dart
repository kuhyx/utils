import 'package:design_system/design_system.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Pumps a screen whose button calls [onPressed] with a context that has a
/// `ScaffoldMessenger` above it.
Future<void> _pumpMessengerScreen(
  WidgetTester tester,
  void Function(BuildContext context) onPressed,
) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: buildDarkTheme(),
      home: Scaffold(
        body: Builder(
          builder: (context) => ElevatedButton(
            onPressed: () => onPressed(context),
            child: const Text('go'),
          ),
        ),
      ),
    ),
  );
}

void main() {
  testWidgets('showToast displays the message', (tester) async {
    await _pumpMessengerScreen(tester, (context) {
      showToast(context, 'Saved');
    });
    await tester.tap(find.text('go'));
    await tester.pump();
    expect(find.text('Saved'), findsOneWidget);
  });

  testWidgets('showToast leaves the background unstyled', (tester) async {
    await _pumpMessengerScreen(tester, (context) {
      showToast(context, 'Saved');
    });
    await tester.tap(find.text('go'));
    await tester.pump();
    final snack = tester.widget<SnackBar>(find.byType(SnackBar));
    expect(snack.backgroundColor, isNull);
    expect(snack.duration, const Duration(seconds: 3));
  });

  testWidgets('showError uses the danger hue and stays up longer', (
    tester,
  ) async {
    await _pumpMessengerScreen(tester, (context) {
      showError(context, 'Sync failed');
    });
    await tester.tap(find.text('go'));
    await tester.pump();

    final snack = tester.widget<SnackBar>(find.byType(SnackBar));
    expect(snack.backgroundColor, AppPalette.danger);
    expect(snack.duration, const Duration(seconds: 5));

    final text = tester.widget<Text>(find.text('Sync failed'));
    expect(text.style?.color, AppPalette.onFill);
  });

  testWidgets('both float and use the shared radius', (tester) async {
    await _pumpMessengerScreen(tester, (context) {
      showToast(context, 'Saved');
    });
    await tester.tap(find.text('go'));
    await tester.pump();

    final snack = tester.widget<SnackBar>(find.byType(SnackBar));
    expect(snack.behavior, SnackBarBehavior.floating);
    expect(
      (snack.shape! as RoundedRectangleBorder).borderRadius,
      BorderRadius.circular(AppRadius.sm),
    );
  });

  testWidgets('a second message replaces the first rather than queueing', (
    tester,
  ) async {
    await _pumpMessengerScreen(tester, (context) {
      showToast(context, 'First');
      showToast(context, 'Second');
    });
    await tester.tap(find.text('go'));
    await tester.pump();

    expect(find.text('First'), findsNothing);
    expect(find.text('Second'), findsOneWidget);
  });

  testWidgets('returns null instead of throwing with no messenger above', (
    tester,
  ) async {
    ScaffoldFeatureController<SnackBar, SnackBarClosedReason>? toast;
    ScaffoldFeatureController<SnackBar, SnackBarClosedReason>? error;
    await tester.pumpWidget(
      Directionality(
        textDirection: TextDirection.ltr,
        child: Builder(
          builder: (context) {
            toast = showToast(context, 'Saved');
            error = showError(context, 'Broke');
            return const SizedBox.shrink();
          },
        ),
      ),
    );
    expect(toast, isNull);
    expect(error, isNull);
  });
}
