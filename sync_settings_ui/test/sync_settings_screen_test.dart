import 'dart:async';

import 'package:crdt_sync/crdt_sync.dart';
import 'package:flutter/material.dart';
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
    binding.platformDispatcher.views.first.physicalSize = const Size(
      800,
      2000,
    );
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
      expect(find.text('Disconnect'), findsOneWidget);
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

      await tester.tap(find.text('Disconnect'));
      await tester.pumpAndSettle();

      expect(cleared, isTrue);
      expect(find.text('Firebase disconnected.'), findsOneWidget);
      expect(find.text('Connect Firebase'), findsOneWidget);
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
      await tester.tap(find.text('Connect Firebase'));
      await tester.pumpAndSettle();

      expect(
        find.text('Enter the sync account email and password.'),
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
        find.widgetWithText(TextField, 'Sync account email'),
        'a@b.com',
      );
      await tester.enterText(
        find.widgetWithText(TextField, 'Sync account password'),
        'pw',
      );
      await tester.tap(find.text('Connect Firebase'));
      await tester.pumpAndSettle();

      expect(find.text('Connected to Firebase.'), findsOneWidget);
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
        find.widgetWithText(TextField, 'Sync account email'),
        'a@b.com',
      );
      await tester.enterText(
        find.widgetWithText(TextField, 'Sync account password'),
        'wrong',
      );
      await tester.tap(find.text('Connect Firebase'));
      await tester.pumpAndSettle();

      expect(find.text('Firebase rejected that account.'), findsOneWidget);
    });

    testWidgets(
      'shows the Google button when googleAvailable, and connecting '
      'succeeds',
      (tester) async {
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

        expect(find.text('Sign in with Google'), findsOneWidget);
        // The password form is collapsed behind its ExpansionTile when
        // Google is offered -- only the field labels prove that; the tile's
        // own title text is present either way.
        expect(
          find.widgetWithText(TextField, 'Sync account email'),
          findsNothing,
        );
        await tester.tap(find.text('Sign in with Google'));
        await tester.pumpAndSettle();

        expect(find.text('Connected to Firebase.'), findsOneWidget);
      },
    );

    testWidgets('Google sign-in cancelled shows the cancellation message', (
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
            googleFirebaseFactory: () async => null,
            googleAvailable: true,
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Sign in with Google'));
      await tester.pumpAndSettle();

      expect(find.text('Google sign-in was cancelled.'), findsOneWidget);
    });

    testWidgets(
      'Google sign-in that does not persist a session reports the retry '
      'message',
      (tester) async {
        await tester.pumpWidget(
          _wrap(
            SyncSettingsScreen(
              accountLoader: () async => null,
              accountSaver: (_) async {},
              accountClearer: () async {},
              sessionProbe: () async => false,
              firebaseFactory: () async => null,
              googleFirebaseFactory: () async => _fakeClient(),
              googleAvailable: true,
            ),
          ),
        );
        await tester.pumpAndSettle();

        await tester.tap(find.text('Sign in with Google'));
        await tester.pumpAndSettle();

        expect(
          find.textContaining('did not save the session'),
          findsOneWidget,
        );
      },
    );

    testWidgets('Google sign-in wrong-account error surfaces the message', (
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
            googleFirebaseFactory: () async =>
                throw FirebaseAuthError('wrong uid'),
            googleAvailable: true,
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Sign in with Google'));
      await tester.pumpAndSettle();

      expect(find.text('wrong uid'), findsOneWidget);
    });

    testWidgets('Google sign-in generic failure surfaces the error text', (
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
            googleFirebaseFactory: () async => throw StateError('boom'),
            googleAvailable: true,
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Sign in with Google'));
      await tester.pumpAndSettle();

      expect(find.textContaining('Google sign-in failed'), findsOneWidget);
    });

    testWidgets(
      'hides the Google button when googleAvailable is true but no '
      'googleFirebaseFactory is wired -- a visible button that can never '
      'succeed must not render',
      (tester) async {
        await tester.pumpWidget(
          _wrap(
            SyncSettingsScreen(
              accountLoader: () async => null,
              accountSaver: (_) async {},
              accountClearer: () async {},
              sessionProbe: () async => false,
              firebaseFactory: () async => null,
              googleAvailable: true,
            ),
          ),
        );
        await tester.pumpAndSettle();

        expect(find.text('Sign in with Google'), findsNothing);
      },
    );
  });

  group('Backup section', () {
    testWidgets('omitted entirely when backup is null', (tester) async {
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

      expect(find.text('Backup'), findsNothing);
    });

    testWidgets('export and import call the injected callbacks', (
      tester,
    ) async {
      var exported = false;
      var imported = false;
      await tester.pumpWidget(
        _wrap(
          SyncSettingsScreen(
            accountLoader: () async => null,
            accountSaver: (_) async {},
            accountClearer: () async {},
            sessionProbe: () async => false,
            firebaseFactory: () async => null,
            backup: BackupSlot(
              label: 'notes',
              export: () async => exported = true,
              import: () async => imported = true,
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Backup'), findsOneWidget);
      await tester.tap(find.text('Export notes'));
      await tester.pumpAndSettle();
      expect(exported, isTrue);
      expect(find.text('Exported notes.'), findsOneWidget);

      await tester.tap(find.text('Import notes'));
      await tester.pumpAndSettle();
      expect(imported, isTrue);
      expect(find.text('Imported notes.'), findsOneWidget);
    });

    testWidgets('export failure reports the error', (tester) async {
      await tester.pumpWidget(
        _wrap(
          SyncSettingsScreen(
            accountLoader: () async => null,
            accountSaver: (_) async {},
            accountClearer: () async {},
            sessionProbe: () async => false,
            firebaseFactory: () async => null,
            backup: BackupSlot(
              label: 'notes',
              export: () async => throw Exception('disk full'),
              import: () async {},
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Export notes'));
      await tester.pumpAndSettle();
      expect(find.textContaining('Export failed'), findsOneWidget);
    });

    testWidgets('import failure reports the error', (tester) async {
      await tester.pumpWidget(
        _wrap(
          SyncSettingsScreen(
            accountLoader: () async => null,
            accountSaver: (_) async {},
            accountClearer: () async {},
            sessionProbe: () async => false,
            firebaseFactory: () async => null,
            backup: BackupSlot(
              label: 'notes',
              export: () async {},
              import: () async => throw Exception('corrupt file'),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Import notes'));
      await tester.pumpAndSettle();
      expect(find.textContaining('Import failed'), findsOneWidget);
    });
  });

  testWidgets('shows a loading indicator until initial load completes', (
    tester,
  ) async {
    final completer = Completer<FirebaseAccount?>();
    await tester.pumpWidget(
      _wrap(
        SyncSettingsScreen(
          accountLoader: () => completer.future,
          accountSaver: (_) async {},
          accountClearer: () async {},
          sessionProbe: () async => false,
          firebaseFactory: () async => null,
        ),
      ),
    );
    await tester.pump();
    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    completer.complete(null);
    await tester.pumpAndSettle();
    expect(find.byType(CircularProgressIndicator), findsNothing);
  });
}
