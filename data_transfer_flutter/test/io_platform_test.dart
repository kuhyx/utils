import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:data_transfer_flutter/src/platform_io.dart';
import 'package:file_selector_platform_interface/file_selector_platform_interface.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:plugin_platform_interface/plugin_platform_interface.dart';

class _FakeSelector extends FileSelectorPlatform
    with MockPlatformInterfaceMixin {
  FileSaveLocation? saveLocation;
  XFile? fileToOpen;
  final saveRequests = <String?>[];

  @override
  Future<FileSaveLocation?> getSaveLocation({
    List<XTypeGroup>? acceptedTypeGroups,
    SaveDialogOptions options = const SaveDialogOptions(),
  }) async {
    saveRequests.add(options.suggestedName);
    return saveLocation;
  }

  @override
  Future<XFile?> openFile({
    List<XTypeGroup>? acceptedTypeGroups,
    String? initialDirectory,
    String? confirmButtonText,
  }) async => fileToOpen;
}

void main() {
  late _FakeSelector selector;
  late Directory temp;

  setUp(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    selector = _FakeSelector();
    FileSelectorPlatform.instance = selector;
    temp = await Directory.systemTemp.createTemp('data_transfer_io');
  });

  tearDown(() => temp.delete(recursive: true));

  group('desktop', () {
    final desktop = IoDataTransferPlatform(isMobile: false);

    test('save writes to the chosen path and suggests the name', () async {
      final path = '${temp.path}/out.json';
      selector.saveLocation = FileSaveLocation(path);

      final saved = await desktop.saveText(fileName: 'x.json', text: '{}');

      expect(saved, isTrue);
      expect(File(path).readAsStringSync(), '{}');
      expect(selector.saveRequests, ['x.json']);
    });

    test('a cancelled save writes nothing and returns false', () async {
      final saved = await desktop.saveText(fileName: 'x.json', text: '{}');

      expect(saved, isFalse);
      expect(temp.listSync(), isEmpty);
    });

    test('share falls back to the save dialog', () async {
      final path = '${temp.path}/shared.json';
      selector.saveLocation = FileSaveLocation(path);

      final shared = await desktop.shareText(fileName: 'x.json', text: '[]');

      expect(shared, isTrue);
      expect(File(path).readAsStringSync(), '[]');
    });

    test('pick reads the chosen file, null when cancelled', () async {
      expect(await desktop.pickText(), isNull);

      selector.fileToOpen = XFile.fromData(
        Uint8List.fromList('{"a":1}'.codeUnits),
        name: 'in.json',
      );

      expect(await desktop.pickText(), '{"a":1}');
    });
  });

  group('mobile', () {
    test(
      'save hands UTF-8 bytes to the document saver, not file_selector',
      () async {
        String? name;
        List<int>? captured;
        final mobile = IoDataTransferPlatform(
          isMobile: true,
          documentSaver: ({required fileName, required bytes}) async {
            name = fileName;
            captured = bytes;
            return true;
          },
        );

        final saved = await mobile.saveText(fileName: 'm.json', text: 'zażółć');

        expect(saved, isTrue);
        expect(name, 'm.json');
        expect(utf8.decode(captured!), 'zażółć');
        expect(selector.saveRequests, isEmpty);
      },
    );

    test('a cancelled document picker reports false', () async {
      final mobile = IoDataTransferPlatform(
        isMobile: true,
        documentSaver: ({required fileName, required bytes}) async => false,
      );

      expect(await mobile.saveText(fileName: 'm.json', text: '{}'), isFalse);
    });

    test('share goes through the share sheet seam', () async {
      (String, String)? seen;
      final mobile = IoDataTransferPlatform(
        isMobile: true,
        sheetSharer: ({required fileName, required text}) async {
          seen = (fileName, text);
          return true;
        },
      );

      expect(await mobile.shareText(fileName: 's.json', text: '1'), isTrue);
      expect(seen, ('s.json', '1'));
    });
  });
}
