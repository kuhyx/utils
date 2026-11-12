import 'dart:async';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:material_ui/material_ui.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sync_settings_ui/sync_settings_ui.dart';

FirebaseRestClient _fakeClient() => FirebaseRestClient(
  databaseUrl: 'https://example.firebasedatabase.app',
  auth: FirebaseTokenProvider(
    apiKey: 'test-key',
    store: InMemoryCredentialStore(),
  ),
);

Widget _wrap(Widget child) => MaterialApp(home: child);

void main() {
  // Every test expands the Google/password ExpansionTile, which pushes the
  // form fields well past the default 800x600 test surface. A taller
  // surface keeps every button reachable without scrolling -- scrolling a
  // plain (non-.builder) ListView far enough still unmounts sliver children
  // beyond its cache extent, which made an early version of these tests
  // lose the Firebase section from the tree entirely.
  setUp(() {
    final binding = TestWidgetsFlutterBinding.ensureInitialized();
    binding.platformDispatcher.views.first.physicalSize = const Size(800, 2000);
    binding.platformDispatcher.views.first.devicePixelRatio = 1.0;
    addTearDown(binding.platformDispatcher.views.first.resetPhysicalSize);
    addTearDown(binding.platformDispatcher.views.first.resetDevicePixelRatio);
  });

  group('Firebase section', () {
    testWidgets('shows connected state with email and Disconnect', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(
          SyncSettingsScreen(
            accountLoader: () async =>
                const FirebaseAccount(email: 'a@b.com', password: 'x'),
            accountSaver: (_) async {},
            accountClearer: () async {},
            sessionProbe: () async => true,
            firebaseFactory: () async => null,
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('a@b.com'), findsOneWidget);
      expect(find.bySemanticsLabel('Disconnect'), findsOneWidget);
    });

    testWidgets('disconnect clears the account and shows status', (
      tester,
    ) async {
      var cleared = false;
      await tester.pumpWidget(
        _wrap(
          SyncSettingsScreen(
            accountLoader: () async =>
                const FirebaseAccount(email: 'a@b.com', password: 'x'),
            accountSaver: (_) async {},
            accountClearer: () async => cleared = true,
            sessionProbe: () async => true,
            firebaseFactory: () async => null,
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.bySemanticsLabel('Disconnect'));
      await tester.pumpAndSettle();

      expect(cleared, isTrue);
      expect(find.bySemanticsLabel('Firebase disconnected.'), findsOneWidget);
      expect(find.bySemanticsLabel('Connect Firebase'), findsOneWidget);
    });

    testWidgets('connect with password shows an error when empty', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(
          SyncSettingsScreen(
            accountLoader: () async => null,
            accountSaver: (_) async {},
            accountClearer: () async {},
            sessionProbe: () async => false,
            firebaseFactory: () async => null,
          ),
        ),
      );
      await tester.pumpAndSettle();

      // Google unavailable by default -> password form starts expanded.
      await tester.tap(find.bySemanticsLabel('Connect Firebase'));
      await tester.pumpAndSettle();

      expect(
        find.bySemanticsLabel('Enter the sync account email and password.'),
        findsOneWidget,
      );
    });

    testWidgets('connect with password succeeds and shows Connected', (
      tester,
    ) async {
      await tester.pumpWidget(
        _wrap(
          SyncSettingsScreen(
            accountLoader: () async => null,
            accountSaver: (_) async {},
            accountClearer: () async {},
            sessionProbe: () async => false,
            firebaseFactory: () async => _fakeClient(),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.enterText(
        find.widgetWithIcon(TextField, Icons.alternate_email),
        'a@b.com',
      );
      await tester.enterText(
        find.widgetWithIcon(TextField, Icons.lock_outline),
        'pw',
      );
      await tester.tap(find.bySemanticsLabel('Connect Firebase'));
      await tester.pumpAndSettle();

      expect(find.bySemanticsLabel('Connected to Firebase.'), findsOneWidget);
      expect(find.text('a@b.com'), findsOneWidget);
    });

    testWidgets('connect with password reports rejection', (tester) async {
      await tester.pumpWidget(
        _wrap(
          SyncSettingsScreen(
            accountLoader: () async => null,
            accountSaver: (_) async {},
            accountClearer: () async {},
            sessionProbe: () async => false,
            firebaseFactory: () async => null,
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.enterText(
        find.widgetWithIcon(TextField, Icons.alternate_email),
        'a@b.com',
      );
      await tester.enterText(
        find.widgetWithIcon(TextField, Icons.lock_outline),
        'wrong',
      );
      await tester.tap(find.bySemanticsLabel('Connect Firebase'));
      await tester.pumpAndSettle();

      expect(
        find.bySemanticsLabel('Firebase rejected that account.'),
        findsOneWidget,
      );
    });

    testWidgets(
      'connect with password does not get stuck on "Signing in..." when '
      'the factory throws -- reproduces the reported hang, where the '
      'button stayed disabled and the status text never changed',
      (tester) async {
        await tester.pumpWidget(
          _wrap(
            SyncSettingsScreen(
              accountLoader: () async => null,
              accountSaver: (_) async {},
              accountClearer: () async {},
              sessionProbe: () async => false,
              firebaseFactory: () async => throw FirebaseAuthError('bad creds'),
            ),
          ),
        );
        await tester.pumpAndSettle();

        await tester.enterText(
          find.widgetWithIcon(TextField, Icons.alternate_email),
          'a@b.com',
        );
        await tester.enterText(
          find.widgetWithIcon(TextField, Icons.lock_outline),
          'wrong',
        );
        await tester.tap(find.bySemanticsLabel('Connect Firebase'));
        await tester.pumpAndSettle();

        expect(find.bySemanticsLabel('Signing in to Firebase…'), findsNothing);
        expect(
          find.bySemanticsLabel('Firebase rejected that account: bad creds'),
          findsOneWidget,
        );
        final button = tester.widget<FilledButton>(
          find.widgetWithIcon(FilledButton, Icons.cloud_done),
        );
        expect(button.onPressed, isNotNull);
      },
    );

    testWidgets('shows the Google button when googleAvailable, and connecting '
        'succeeds', (tester) async {
      var sessionStored = false;
      await tester.pumpWidget(
        _wrap(
          SyncSettingsScreen(
            accountLoader: () async => null,
            accountSaver: (_) async {},
            accountClearer: () async {},
            sessionProbe: () async => sessionStored,
            firebaseFactory: () async => null,
            googleFirebaseFactory: () async {
              sessionStored = true;
              return _fakeClient();
            },
            googleAvailable: true,
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.bySemanticsLabel('Sign in with Google'), findsOneWidget);
      // The password form is collapsed behind its ExpansionTile when
      // Google is offered -- only the field labels prove that; the tile's
      // own title text is present either way.
      expect(
        find.widgetWithIcon(TextField, Icons.alternate_email),
        findsNothing,
      );
      await tester.tap(find.bySemanticsLabel('Sign in with Google'));
      await tester.pumpAndSettle();

      expect(find.bySemanticsLabel('Connected to Firebase.'), findsOneWidget);
    });
  });
}
