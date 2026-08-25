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
  group('Firebase section Google sign-in', () {
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

      expect(find.textContaining('Sign-in failed'), findsOneWidget);
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

    testWidgets('a reason renders a disabled button that explains itself', (
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
            googleFirebaseFactory: () async => _fakeClient(),
            googleAvailable: false,
            googleUnavailableReason: 'Not available on this platform.',
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Sign in with Google'), findsOneWidget);
      expect(find.text('Not available on this platform.'), findsOneWidget);

      // Disabled, so it cannot report a misleading "cancelled".
      final button = tester.widget<FilledButton>(
        find.widgetWithText(FilledButton, 'Sign in with Google'),
      );
      expect(button.onPressed, isNull);
    });

    testWidgets('no reason keeps the button hidden, as before', (
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
            googleFirebaseFactory: () async => _fakeClient(),
            googleAvailable: false,
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Sign in with Google'), findsNothing);
    });
  });
}
