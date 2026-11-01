import 'dart:convert';

import 'package:data_transfer_flutter/src/envelope.dart';
import 'package:data_transfer_flutter/src/platform.dart';
import 'package:data_transfer_flutter/src/platform_default.dart';

/// Holds the platform the top-level functions use; tests replace it.
abstract final class DataTransfer {
  /// The active platform. Defaults to the host's real implementation.
  static DataTransferPlatform platform = createDefaultPlatform();
}

const _pretty = JsonEncoder.withIndent('  ');

/// Saves [json] as [fileName] to device storage (see
/// [DataTransferPlatform.saveText]). False when the user cancelled.
Future<bool> exportJson({
  required String fileName,
  required Map<String, Object?> json,
}) => exportJsonText(fileName: fileName, text: _pretty.convert(json));

/// [exportJson] for an already-encoded JSON string.
Future<bool> exportJsonText({required String fileName, required String text}) =>
    DataTransfer.platform.saveText(fileName: fileName, text: text);

/// Optional second action: offers [json] to the share sheet.
Future<bool> shareJson({
  required String fileName,
  required Map<String, Object?> json,
}) => DataTransfer.platform.shareText(
  fileName: fileName,
  text: _pretty.convert(json),
);

/// Lets the user pick a JSON file and decodes it; null when cancelled.
///
/// Throws [EnvelopeInvalidJson] / [EnvelopeNotObject] for a file that is not
/// a JSON object.
Future<Map<String, Object?>?> pickJson() async {
  final text = await pickJsonText();
  if (text == null) return null;
  final Object? decoded;
  try {
    decoded = jsonDecode(text);
  } on FormatException {
    throw const EnvelopeInvalidJson();
  }
  if (decoded is! Map<String, Object?>) throw const EnvelopeNotObject();
  return decoded;
}

/// Lets the user pick a file and returns its raw text; null when cancelled.
Future<String?> pickJsonText() => DataTransfer.platform.pickText();
