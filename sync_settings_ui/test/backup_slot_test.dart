import 'dart:convert';

import 'package:data_transfer_flutter/data_transfer_flutter.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sync_settings_ui/sync_settings_ui.dart';

void main() {
  test('carries the label and invokes the injected callbacks', () async {
    var exported = false;
    var imported = false;
    final slot = BackupSlot(
      label: 'notes',
      export: () async => exported = true,
      import: () async => imported = true,
    );
    expect(slot.label, 'notes');
    await slot.export();
    await slot.import();
    expect(exported, isTrue);
    expect(imported, isTrue);
  });

  group('BackupSlot.json', () {
    late _FakePlatform fake;
    late DataTransferPlatform original;

    setUp(() {
      original = DataTransfer.platform;
      fake = _FakePlatform();
      DataTransfer.platform = fake;
    });

    tearDown(() => DataTransfer.platform = original);

    test('export saves the built map under fileName', () async {
      final slot = BackupSlot.json(
        label: 'inventory',
        fileName: 'inv.json',
        build: () async => {'items': 3},
        restore: (_) async {},
      );

      await slot.export();

      expect(fake.saved.single.$1, 'inv.json');
      expect(jsonDecode(fake.saved.single.$2), {'items': 3});
    });

    test('import hands the picked map to restore', () async {
      fake.picked = '{"items":3}';
      Map<String, Object?>? restored;
      final slot = BackupSlot.json(
        label: 'inventory',
        fileName: 'inv.json',
        build: () async => {},
        restore: (json) async => restored = json,
      );

      await slot.import();

      expect(restored, {'items': 3});
    });

    test('a cancelled picker restores nothing', () async {
      var called = false;
      final slot = BackupSlot.json(
        label: 'inventory',
        fileName: 'inv.json',
        build: () async => {},
        restore: (_) async => called = true,
      );

      await slot.import();

      expect(called, isFalse);
    });
  });
}

class _FakePlatform implements DataTransferPlatform {
  String? picked;
  final saved = <(String, String)>[];

  @override
  Future<bool> saveText({
    required String fileName,
    required String text,
    String mimeType = 'application/json',
  }) async {
    saved.add((fileName, text));
    return true;
  }

  @override
  Future<bool> shareText({
    required String fileName,
    required String text,
    String mimeType = 'application/json',
  }) async => true;

  @override
  Future<String?> pickText() async => picked;
}
