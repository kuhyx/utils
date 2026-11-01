import 'dart:convert';

import 'package:data_transfer_flutter/src/json_type_group.dart';
import 'package:data_transfer_flutter/src/platform.dart';
import 'package:file_selector/file_selector.dart';

/// The browser's platform: downloads and the open-file dialog.
DataTransferPlatform createDefaultPlatform() => const WebDataTransferPlatform();

/// Browser implementation. No share sheet; download covers both actions.
class WebDataTransferPlatform implements DataTransferPlatform {
  /// Creates the platform.
  const WebDataTransferPlatform();

  @override
  Future<bool> saveText({
    required String fileName,
    required String text,
    String mimeType = 'application/json',
  }) async {
    // `saveTo` on web clicks a synthetic anchor: the path is ignored and the
    // browser's download UI decides where the file lands.
    await XFile.fromData(
      utf8.encode(text),
      mimeType: mimeType,
      name: fileName,
    ).saveTo('');
    return true;
  }

  @override
  Future<bool> shareText({
    required String fileName,
    required String text,
    String mimeType = 'application/json',
  }) => saveText(fileName: fileName, text: text, mimeType: mimeType);

  @override
  Future<String?> pickText() async {
    final file = await openFile(acceptedTypeGroups: const [jsonTypeGroup]);
    return await file?.readAsString();
  }
}
