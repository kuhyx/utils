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
  group('Backup section', () {
    testWidgets('a cancelled export or import claims no success', (
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
            backup: BackupSlot(
              label: 'notes',
              export: () async => throw const BackupCancelled(),
              import: () async => throw const BackupCancelled(),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.bySemanticsLabel('Export notes'));
      await tester.pumpAndSettle();
      expect(find.bySemanticsLabel('Exported notes.'), findsNothing);
      expect(spoken('failed'), findsNothing);

      await tester.tap(find.bySemanticsLabel('Import notes'));
      await tester.pumpAndSettle();
      expect(find.bySemanticsLabel('Imported notes.'), findsNothing);
      expect(spoken('failed'), findsNothing);
    });

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

      expect(find.bySemanticsLabel('Backup'), findsNothing);
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

      expect(find.bySemanticsLabel('Backup'), findsOneWidget);
      await tester.tap(find.bySemanticsLabel('Export notes'));
      await tester.pumpAndSettle();
      expect(exported, isTrue);
      expect(find.bySemanticsLabel('Exported notes.'), findsOneWidget);

      await tester.tap(find.bySemanticsLabel('Import notes'));
      await tester.pumpAndSettle();
      expect(imported, isTrue);
      expect(find.bySemanticsLabel('Imported notes.'), findsOneWidget);
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

      await tester.tap(find.bySemanticsLabel('Export notes'));
      await tester.pumpAndSettle();
      expect(spoken('Export failed'), findsOneWidget);
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

      await tester.tap(find.bySemanticsLabel('Import notes'));
      await tester.pumpAndSettle();
      expect(spoken('Import failed'), findsOneWidget);
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

/// A node whose spoken label contains [part] literally.
Finder spoken(String part) =>
    find.bySemanticsLabel(RegExp(RegExp.escape(part)));
