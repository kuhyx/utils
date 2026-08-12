/// An injectable local export/import delegate for [SyncSettingsScreen]'s
/// optional "Backup" section.
///
/// Deliberately not a shared implementation: the actual export/import format
/// differs per app (todo: Markdown notes; home_inventory: inventory export;
/// workout_app: a permission-gated `BackupService`), so this package only
/// carries the label and the two callbacks. Passing `null` for
/// `SyncSettingsScreen.backup` omits the section entirely (diet_guard,
/// wake_alarm have no local backup at all).
class BackupSlot {
  /// Creates a [BackupSlot] labelled [label] (e.g. `'notes'`,
  /// `'inventory'`), backed by [export] and [import].
  const BackupSlot({
    required this.label,
    required this.export,
    required this.import,
  });

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
