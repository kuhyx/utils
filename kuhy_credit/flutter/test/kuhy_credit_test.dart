import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:kuhy_credit/kuhy_credit.dart';
import 'package:plugin_platform_interface/plugin_platform_interface.dart';
import 'package:url_launcher_platform_interface/url_launcher_platform_interface.dart';

final Finder _logo = find.byKey(KuhyCredit.logoKey);
final Finder _panel = find.byKey(KuhyCredit.panelKey);

Future<List<Uri>> _pump(
  WidgetTester tester, {
  Brightness brightness = Brightness.dark,
  bool below = false,
  bool alignStart = false,
  Alignment at = Alignment.bottomRight,
}) async {
  final opened = <Uri>[];
  tester.platformDispatcher.platformBrightnessTestValue = brightness;
  addTearDown(tester.platformDispatcher.clearPlatformBrightnessTestValue);
  await tester.pumpWidget(
    WidgetsApp(
      color: const Color(kDarkBg),
      pageRouteBuilder: _route,
      home: Stack(
        children: [
          const Positioned(
            left: 0,
            top: 0,
            child: SizedBox(width: 40, height: 40),
          ),
          Align(
            alignment: at,
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: KuhyCredit(
                below: below,
                alignStart: alignStart,
                launcher: (uri) async => opened.add(uri),
              ),
            ),
          ),
        ],
      ),
    ),
  );
  return opened;
}

PageRoute<T> _route<T>(RouteSettings settings, WidgetBuilder builder) =>
    PageRouteBuilder<T>(
      settings: settings,
      pageBuilder: (context, _, _) => builder(context),
    );

void main() {
  testWidgets('shows only the logo, named for screen readers', (tester) async {
    final handle = tester.ensureSemantics();
    final opened = await _pump(tester);
    expect(_logo, findsOneWidget);
    expect(_panel, findsNothing);
    expect(find.text(kCreditText), findsNothing);
    expect(find.bySemanticsLabel(kCreditText), findsOneWidget);
    expect(opened, isEmpty);
    handle.dispose();
  });

  testWidgets('logo tap opens the panel; panel tap opens the site', (
    tester,
  ) async {
    final opened = await _pump(tester);
    await tester.tap(_logo);
    await tester.pumpAndSettle();
    expect(_panel, findsOneWidget);
    expect(find.text(kCreditText), findsOneWidget);
    expect(opened, isEmpty);
    await tester.tap(find.text(kCreditText));
    await tester.pumpAndSettle();
    expect(opened, [Uri.parse(kCreditUrl)]);
    expect(_panel, findsNothing);
  });

  testWidgets('second logo tap closes and stays closed', (tester) async {
    final opened = await _pump(tester);
    await tester.tap(_logo);
    await tester.pumpAndSettle();
    await tester.tap(_logo);
    await tester.pumpAndSettle();
    expect(_panel, findsNothing);
    expect(opened, isEmpty);
  });

  testWidgets('tap outside closes', (tester) async {
    final opened = await _pump(tester);
    await tester.tap(_logo);
    await tester.pumpAndSettle();
    await tester.tapAt(const Offset(10, 10));
    await tester.pumpAndSettle();
    expect(_panel, findsNothing);
    expect(opened, isEmpty);
  });

  testWidgets('Escape closes and returns focus to the logo', (tester) async {
    final opened = await _pump(tester);
    await tester.tap(_logo);
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.escape);
    await tester.pumpAndSettle();
    expect(_panel, findsNothing);
    expect(opened, isEmpty);
    expect(
      Focus.of(tester.element(find.byKey(KuhyCredit.logoKey))).hasFocus,
      isTrue,
    );
  });

  testWidgets('Back closes the panel instead of leaving the screen', (
    tester,
  ) async {
    await _pump(tester);
    await tester.tap(_logo);
    await tester.pumpAndSettle();
    final handled = await tester.binding.handlePopRoute();
    await tester.pumpAndSettle();
    expect(handled, isTrue);
    expect(_panel, findsNothing);
  });

  testWidgets('keyboard: Tab reaches the logo, Enter opens, Enter on panel '
      'opens the site', (tester) async {
    final opened = await _pump(tester);
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();
    expect(_panel, findsOneWidget);
    await tester.sendKeyEvent(LogicalKeyboardKey.space);
    await tester.pumpAndSettle();
    expect(opened, [Uri.parse(kCreditUrl)]);
  });

  testWidgets('other keys leave the panel open', (tester) async {
    await _pump(tester);
    await tester.tap(_logo);
    await tester.pumpAndSettle();
    await tester.sendKeyEvent(LogicalKeyboardKey.keyA);
    await tester.pumpAndSettle();
    expect(_panel, findsOneWidget);
  });

  for (final (brightness, surface, text) in [
    (Brightness.dark, kDarkSurface, kDarkText),
    (Brightness.light, kLightSurface, kLightText),
  ]) {
    testWidgets('panel colours follow $brightness tokens', (tester) async {
      await _pump(tester, brightness: brightness);
      await tester.tap(_logo);
      await tester.pumpAndSettle();
      final box = tester.widget<DecoratedBox>(
        find.descendant(of: _panel, matching: find.byType(DecoratedBox)),
      );
      final deco = box.decoration as BoxDecoration;
      expect(deco.color, Color(surface));
      expect(deco.borderRadius, BorderRadius.circular(kRadius));
      final style = tester.widget<Text>(find.text(kCreditText)).style!;
      expect(style.color, Color(text));
      expect(style.fontSize, kTextBody);
    });
  }

  testWidgets('panel sits above and end-aligned by default', (tester) async {
    await _pump(tester);
    await tester.tap(_logo);
    await tester.pumpAndSettle();
    final panel = tester.getRect(_panel);
    final logo = tester.getRect(_logo);
    expect(panel.bottom, lessThan(logo.top));
    expect(panel.right, moreOrLessEquals(logo.right));
  });

  testWidgets('below + alignStart puts it under, start-aligned', (
    tester,
  ) async {
    await _pump(tester, below: true, alignStart: true, at: Alignment.topLeft);
    await tester.tap(_logo);
    await tester.pumpAndSettle();
    final panel = tester.getRect(_panel);
    final logo = tester.getRect(_logo);
    expect(panel.top, greaterThan(logo.bottom));
    expect(panel.left, moreOrLessEquals(logo.left));
  });

  testWidgets('the default launcher opens a new tab / external app', (
    tester,
  ) async {
    final fake = _FakeLauncher();
    UrlLauncherPlatform.instance = fake;
    await tester.pumpWidget(
      WidgetsApp(
        color: const Color(kDarkBg),
        pageRouteBuilder: _route,
        home: const Center(child: KuhyCredit()),
      ),
    );
    await tester.tap(_logo);
    await tester.pumpAndSettle();
    await tester.tap(find.text(kCreditText));
    await tester.pumpAndSettle();
    expect(fake.urls, [kCreditUrl]);
    expect(fake.options.single.mode, PreferredLaunchMode.externalApplication);
    expect(fake.options.single.webOnlyWindowName, '_blank');
  });

  testWidgets('the logo painter draws and never repaints', (tester) async {
    await _pump(tester);
    final paint = tester.widget<CustomPaint>(
      find.descendant(of: _logo, matching: find.byType(CustomPaint)).first,
    );
    expect(paint.painter!.shouldRepaint(paint.painter!), isFalse);
  });
}

class _FakeLauncher extends Fake
    with MockPlatformInterfaceMixin
    implements UrlLauncherPlatform {
  final urls = <String>[];
  final options = <LaunchOptions>[];

  @override
  Future<bool> launchUrl(String url, LaunchOptions options) async {
    urls.add(url);
    this.options.add(options);
    return true;
  }
}
