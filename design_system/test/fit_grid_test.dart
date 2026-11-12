import 'package:design_system/design_system.dart';
import 'package:material_ui/material_ui.dart';
import 'package:flutter_test/flutter_test.dart';

final _dot = find.byWidgetPredicate(
  (w) => switch (w.key) {
    ValueKey<String>(:final value) => value.startsWith('fit-grid-dot'),
    _ => false,
  },
);

Future<void> _pump(
  WidgetTester tester, {
  required int count,
  Size size = const Size(300, 400),
  int columns = 3,
  double labelHeight = 20,
  double minSquare = 1,
}) {
  return tester.pumpWidget(
    MaterialApp(
      home: Center(
        child: SizedBox.fromSize(
          size: size,
          child: FitGrid(
            itemCount: count,
            columns: columns,
            labelHeight: labelHeight,
            minSquare: minSquare,
            itemBuilder: (context, i) =>
                Container(key: ValueKey('cell-$i'), child: Text('item $i')),
          ),
        ),
      ),
    ),
  );
}

int _onScreen(WidgetTester tester) => find
    .textContaining('item ')
    .evaluate()
    .where((e) => find.byWidget(e.widget).hitTestable().evaluate().isNotEmpty)
    .length;

void main() {
  testWidgets('few items: one page, no dots, nothing overflows', (
    tester,
  ) async {
    await _pump(tester, count: 4);
    expect(_onScreen(tester), 4);
    expect(_dot, findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('rows come from the height: taller box fits more per page', (
    tester,
  ) async {
    await _pump(tester, count: 60, size: const Size(300, 300));
    final short = _onScreen(tester);
    await _pump(tester, count: 60, size: const Size(300, 600));
    final tall = _onScreen(tester);
    expect(short % 3, 0);
    expect(tall, greaterThan(short));
  });

  testWidgets('leftover height goes into the cells: grid fills the box', (
    tester,
  ) async {
    await _pump(tester, count: 9);
    expect(_onScreen(tester), 9);
    final box = tester.getRect(find.byType(FitGrid));
    final last = tester.getRect(find.byKey(const ValueKey('cell-8')));
    expect(last.bottom, closeTo(box.bottom, 1));
    final first = tester.getRect(find.byKey(const ValueKey('cell-0')));
    expect(first.height, greaterThan(first.width + 20));
  });

  testWidgets('minSquare lets a row be shorter than column + label', (
    tester,
  ) async {
    await _pump(tester, count: 60, size: const Size(300, 400), labelHeight: 40);
    final full = _onScreen(tester);
    await _pump(
      tester,
      count: 60,
      size: const Size(300, 400),
      labelHeight: 40,
      minSquare: 0.6,
    );
    expect(_onScreen(tester), greaterThan(full));
    final cell = tester.getRect(find.byKey(const ValueKey('cell-0')));
    final colW = cell.width;
    expect(cell.height, greaterThanOrEqualTo(colW * 0.6 + 40 - 0.5));
    expect(cell.height, lessThan(colW + 40));
  });

  testWidgets('paged grid fills the box above the dots', (tester) async {
    await _pump(tester, count: 40);
    final perPage = _onScreen(tester);
    final box = tester.getRect(find.byType(FitGrid));
    final last = tester.getRect(find.byKey(ValueKey('cell-${perPage - 1}')));
    expect(last.bottom, closeTo(box.bottom - 20, 1));
    final dot = tester.getRect(_dot.first);
    expect(dot.top - last.bottom, lessThan(12));
  });

  testWidgets('cells are square plus the label, within the box', (
    tester,
  ) async {
    await _pump(tester, count: 3);
    final cell = tester.getSize(find.text('item 0').first);
    expect(cell.width, greaterThan(0));
    final box = tester.getRect(find.byType(FitGrid));
    final last = tester.getRect(find.text('item 2'));
    expect(box.contains(last.center), isTrue);
  });

  testWidgets('overflow goes to more pages with one dot per page', (
    tester,
  ) async {
    await _pump(tester, count: 30);
    final perPage = _onScreen(tester);
    expect(perPage, lessThan(30));
    final pages = (30 / perPage).ceil();
    expect(_dot, findsNWidgets(pages));
    expect(find.text('item $perPage').hitTestable(), findsNothing);
  });

  testWidgets('more than 12 pages: "n / N" counter instead of dots', (
    tester,
  ) async {
    await _pump(tester, count: 30);
    final perPage = _onScreen(tester);
    final count = perPage * 13;
    await _pump(tester, count: count);
    expect(_dot, findsNothing);
    final counter = find.byKey(const ValueKey('fit-grid-page-counter'));
    expect(tester.widget<Text>(counter).data, '1 / 13');
    await tester.fling(find.byType(PageView), const Offset(-250, 0), 1000);
    await tester.pumpAndSettle();
    expect(tester.widget<Text>(counter).data, '2 / 13');
    expect(tester.takeException(), isNull);
  });

  testWidgets('exactly 12 pages still shows dots', (tester) async {
    await _pump(tester, count: 30);
    final perPage = _onScreen(tester);
    await _pump(tester, count: perPage * 12);
    expect(_dot, findsNWidgets(12));
    expect(tester.takeException(), isNull);
  });

  testWidgets('swiping left shows the next page and moves the dot', (
    tester,
  ) async {
    await _pump(tester, count: 30);
    final perPage = _onScreen(tester);
    Color? active() {
      final colors = [
        for (final e in _dot.evaluate())
          ((e.widget as Container).decoration! as BoxDecoration).color,
      ];
      return colors.first;
    }

    final before = active();
    await tester.fling(find.byType(PageView), const Offset(-250, 0), 1000);
    await tester.pumpAndSettle();
    expect(find.text('item $perPage').hitTestable(), findsOneWidget);
    expect(find.text('item 0').hitTestable(), findsNothing);
    expect(active(), isNot(before));
  });

  testWidgets('the last page keeps cell size (partial rows are padded)', (
    tester,
  ) async {
    await _pump(tester, count: 30);
    final perPage = _onScreen(tester);
    final firstWidth = tester.getSize(find.text('item 0')).width;
    for (var i = 0; i < 20; i++) {
      await tester.fling(find.byType(PageView), const Offset(-250, 0), 1000);
      await tester.pumpAndSettle();
    }
    expect(find.text('item 29').hitTestable(), findsOneWidget);
    expect(tester.getSize(find.text('item 29')).width, firstWidth);
    expect(perPage, greaterThan(0));
  });

  testWidgets('a box shorter than one row still shows a row', (tester) async {
    await _pump(tester, count: 6, size: const Size(300, 60));
    expect(find.text('item 0'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('list shrinking drops the page back inside the range', (
    tester,
  ) async {
    await _pump(tester, count: 30);
    await tester.fling(find.byType(PageView), const Offset(-250, 0), 1000);
    await tester.pumpAndSettle();
    await _pump(tester, count: 2);
    await tester.pumpAndSettle();
    expect(find.text('item 0').hitTestable(), findsOneWidget);
    expect(_dot, findsNothing);
  });

  testWidgets('empty list renders nothing and does not throw', (tester) async {
    await _pump(tester, count: 0);
    expect(find.textContaining('item '), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('columns is honoured', (tester) async {
    await _pump(tester, count: 6, columns: 2);
    final x0 = tester.getTopLeft(find.text('item 0')).dx;
    final x1 = tester.getTopLeft(find.text('item 1')).dx;
    final x2 = tester.getTopLeft(find.text('item 2')).dx;
    expect(x1, greaterThan(x0));
    expect(x2, x0);
  });
}
