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
