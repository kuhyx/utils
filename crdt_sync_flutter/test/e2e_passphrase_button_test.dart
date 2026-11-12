import 'package:crdt_sync_flutter/crdt_sync_flutter.dart';
import 'package:crdt_sync_flutter/testing/fake_secure_storage.dart';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(installFakeSecureStorage);

  Future<void> pump(WidgetTester t, {required bool locked, VoidCallback? cb}) =>
      t.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: E2ePassphraseButton(locked: locked, onSaved: cb),
          ),
        ),
      );

  testWidgets('icon follows the locked flag', (t) async {
    await pump(t, locked: true);
    expect(find.byIcon(Icons.lock), findsOneWidget);
    await pump(t, locked: false);
    expect(find.byIcon(Icons.lock_open), findsOneWidget);
  });

  testWidgets('entering a passphrase stores it and notifies', (t) async {
    var saved = 0;
    await pump(t, locked: true, cb: () => saved++);
    await t.tap(find.byType(IconButton));
    await t.pumpAndSettle();
    await t.enterText(find.byType(TextField), 'pw');
    await t.tap(find.byIcon(Icons.check));
    await t.pumpAndSettle();
    expect(
      await const FlutterSecureStorage().read(key: kE2ePassphraseKey),
      'pw',
    );
    expect(saved, 1);
  });

  testWidgets('submitting with Enter saves; empty input saves nothing', (
    t,
  ) async {
    await pump(t, locked: true);
    await t.tap(find.byType(IconButton));
    await t.pumpAndSettle();
    await t.enterText(find.byType(TextField), 'x1');
    await t.testTextInput.receiveAction(TextInputAction.done);
    await t.pumpAndSettle();
    expect(
      await const FlutterSecureStorage().read(key: kE2ePassphraseKey),
      'x1',
    );
    await clearE2ePassphrase();
    await t.tap(find.byType(IconButton));
    await t.pumpAndSettle();
    await t.tap(find.byIcon(Icons.check));
    await t.pumpAndSettle();
    expect(
      await const FlutterSecureStorage().read(key: kE2ePassphraseKey),
      isNull,
    );
  });
}
