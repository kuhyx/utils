import 'package:data_transfer_flutter/data_transfer_flutter.dart';

/// Thrown by a [BackupSlot] callback when the user dismissed the file dialog.
///
/// Not a failure: [SyncSettingsScreen] clears its status line instead of
/// claiming success or showing an error.
class BackupCancelled implements Exception {
  /// Creates the signal.
  const new();
}

/// An injectable local export/import delegate for [SyncSettingsScreen]'s
/// optional "Backup" section.
///
/// The export/import CONTENT differs per app (todo: Markdown notes;
/// home_inventory: inventory export; workout_app: a permission-gated
/// `BackupService`), so the default constructor only carries the label and
/// the two callbacks. Apps whose backup is a JSON file use [BackupSlot.json],
/// which adds the shared file plumbing (`data_transfer_flutter`). Passing
/// `null` for `SyncSettingsScreen.backup` omits the section entirely
/// (diet_guard, wake_alarm have no local backup at all).
class BackupSlot {
  /// Creates a [BackupSlot] labelled [label] (e.g. `'notes'`,
  /// `'inventory'`), backed by [export] and [import].
  const new({required this.label, required this.export, required this.import});

  /// A slot whose backup is a JSON file, using `data_transfer_flutter`.
  ///
  /// Export saves `build()` as [fileName] to device storage (system Save-as
  /// on Android/iOS, a save dialog on desktop, a download on web). Import
  /// lets the user pick a JSON file and hands the decoded object to
  /// [restore]. A dismissed dialog throws [BackupCancelled] (and a cancelled
  /// picker restores nothing).
  factory json({
    required String label,
    required String fileName,
    required Future<Map<String, Object?>> Function() build,
    required Future<void> Function(Map<String, Object?> json) restore,
  }) => BackupSlot(
    label: label,
    export: () async {
      final saved = await exportJson(fileName: fileName, json: await build());
      if (!saved) throw const BackupCancelled();
    },
    import: () async {
      final json = await pickJson();
      if (json == null) throw const BackupCancelled();
      await restore(json);
    },
  );

  /// Noun describing what this exports/imports, used in the section's
  /// button text ("Export $label" / "Import $label").
  final String label;

  /// Writes every local record to the app's chosen destination (a share
  /// sheet on mobile, a fixed file path on desktop -- the app's choice, not
  /// this package's).
  final Future<void> Function() export;

  /// Reads records back from wherever [export] wrote them.
  final Future<void> Function() import;
}
