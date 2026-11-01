import 'package:file_selector/file_selector.dart';

/// The type group the open and save dialogs restrict to.
const jsonTypeGroup = XTypeGroup(
  label: 'JSON',
  extensions: ['json'],
  // Needed by the macOS/iOS pickers and harmless elsewhere; a group with no
  // recognised identifier silently matches nothing on those hosts.
  uniformTypeIdentifiers: ['public.json'],
  mimeTypes: ['application/json'],
);

/// The save-dialog filter for [fileName] holding [mimeType] data.
///
/// Keyed on the file's own extension so a CSV export is not offered under a
/// JSON filter; a name with no extension accepts any type.
XTypeGroup saveTypeGroup(String fileName, String mimeType) {
  final dot = fileName.lastIndexOf('.');
  final extension = dot > 0 && dot < fileName.length - 1
      ? fileName.substring(dot + 1).toLowerCase()
      : null;
  return XTypeGroup(
    label: extension?.toUpperCase(),
    extensions: extension == null ? null : [extension],
    mimeTypes: [mimeType],
  );
}
