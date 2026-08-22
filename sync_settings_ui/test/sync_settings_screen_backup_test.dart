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
