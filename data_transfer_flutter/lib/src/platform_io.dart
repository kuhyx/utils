import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:data_transfer_flutter/src/json_type_group.dart';
import 'package:data_transfer_flutter/src/platform.dart';
import 'package:file_picker/file_picker.dart';
import 'package:file_selector/file_selector.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

/// Writes [bytes] through the system "Save as" picker; false on cancel.
typedef DocumentSaver =
    Future<bool> Function({required String fileName, required Uint8List bytes});

/// Offers [text] as a file named [fileName] to the share sheet.
typedef SheetSharer =
    Future<bool> Function({required String fileName, required String text});

/// The platform for hosts that have `dart:io`.
DataTransferPlatform createDefaultPlatform() => IoDataTransferPlatform();

/// Android, iOS and desktop.
///
/// Mobile saves through the Storage Access Framework / document picker
/// (`file_picker`'s `saveFile`), because the share sheet on a stock phone has
/// no local save target and an export that can only be shared is an upload.
/// Desktop uses `file_selector`'s save dialog. Opening is `file_selector`'s
/// `openFile` everywhere: ACTION_OPEN_DOCUMENT on Android.
class IoDataTransferPlatform implements DataTransferPlatform {
  /// Creates the platform; every argument is a test seam.
  IoDataTransferPlatform({
    bool? isMobile,
    DocumentSaver? documentSaver,
    SheetSharer? sheetSharer,
  }) : _isMobile = isMobile ?? (Platform.isAndroid || Platform.isIOS),
       _documentSaver = documentSaver ?? _saveViaDocumentPicker,
       _sheetSharer = sheetSharer ?? _shareViaSheet;

  final bool _isMobile;
  final DocumentSaver _documentSaver;
  final SheetSharer _sheetSharer;

  @override
  Future<bool> saveText({
    required String fileName,
    required String text,
  }) async {
    if (_isMobile) {
      return await _documentSaver(
        fileName: fileName,
        bytes: Uint8List.fromList(utf8.encode(text)),
      );
    }
    final location = await getSaveLocation(
      suggestedName: fileName,
      acceptedTypeGroups: const [jsonTypeGroup],
    );
    if (location == null) return false;
    await File(location.path).writeAsString(text);
    return true;
  }

  @override
  Future<bool> shareText({required String fileName, required String text}) =>
      _isMobile
      ? _sheetSharer(fileName: fileName, text: text)
      : saveText(fileName: fileName, text: text);

  @override
  Future<String?> pickText() async {
    final file = await openFile(acceptedTypeGroups: const [jsonTypeGroup]);
    return await file?.readAsString();
  }
}

// coverage:ignore-start
// Real plugin calls: unreachable on the Linux test host (a platform channel
// answers nothing there) and faked at the typedef seams above instead.
Future<bool> _saveViaDocumentPicker({
  required String fileName,
  required Uint8List bytes,
}) async {
  final saved = await FilePicker.saveFile(
    fileName: fileName,
    bytes: bytes,
    mimeType: 'application/json',
  );
  return saved != null;
}

Future<bool> _shareViaSheet({
  required String fileName,
  required String text,
}) async {
  final dir = await getTemporaryDirectory();
  final file = File(p.join(dir.path, fileName));
  await file.writeAsString(text);
  await SharePlus.instance.share(
    ShareParams(files: [XFile(file.path, mimeType: 'application/json')]),
  );
  return true;
}
// coverage:ignore-end
