/// What differs per host: where the bytes of an export go and come from.
///
/// The seam tests fake. Real implementations live in `platform_io.dart`
/// (Android, iOS, desktop) and `platform_web.dart`, chosen by
/// `platform_default.dart` so no `dart:io` import reaches a web build.
abstract interface class DataTransferPlatform {
  /// Saves [text] as [fileName] where the user can find it again.
  ///
  /// Android/iOS: the system "Save as" document picker (device storage).
  /// Desktop: a save dialog. Web: a browser download. Returns false when the
  /// user cancelled.
  Future<bool> saveText({
    required String fileName,
    required String text,
    String mimeType = 'application/json',
  });

  /// Offers [text] as [fileName] to the share sheet, where the host has one.
  ///
  /// A second action only: a share sheet can route the data to cloud apps, so
  /// it never replaces [saveText]. Hosts without a sheet fall back to
  /// [saveText].
  Future<bool> shareText({
    required String fileName,
    required String text,
    String mimeType = 'application/json',
  });

  /// Opens the system open-document picker and returns the file's text, or
  /// null when the user cancelled.
  Future<String?> pickText();
}
