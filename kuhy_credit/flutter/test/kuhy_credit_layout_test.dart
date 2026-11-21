import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kuhy_credit/kuhy_credit.dart';

void main() {
  testWidgets('a stretching parent (ListView) keeps the logo at its size', (
    tester,
  ) async {
    await tester.pumpWidget(
      WidgetsApp(
        color: const Color(kDarkBg),
        pageRouteBuilder: <T>(settings, builder) => PageRouteBuilder<T>(
          settings: settings,
          pageBuilder: (context, _, _) => builder(context),
        ),
        home: ListView(children: const [KuhyCredit(size: 40)]),
      ),
    );
    final logo = find.byKey(KuhyCredit.logoKey);
    expect(tester.getSize(logo), const Size(40, 40));
    // The tap target shrank with the logo: the row's far end opens nothing.
    final row = tester.getRect(find.byType(KuhyCredit));
    await tester.tapAt(row.centerRight - const Offset(4, 0));
    await tester.pumpAndSettle();
    expect(find.byKey(KuhyCredit.panelKey), findsNothing);
  });
}
