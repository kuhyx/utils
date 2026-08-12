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
}
