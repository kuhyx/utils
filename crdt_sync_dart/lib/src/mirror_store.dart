/// A [RemoteStore] that writes to two backends and reads from both.
///
/// Exists for the GitHub -> Firebase cutover: each app can move to Firebase
/// while still mirroring to the old repo, so rolling back is a constructor
/// change rather than a data recovery.
library;

import 'remote_store.dart';

/// Called when the mirror backend fails, so the failure is loud but survivable.
typedef MirrorFailureHandler =
    void Function(String operation, Object error);

/// Writes to both backends; reads from both and prefers the primary.
///
/// **Reads consult both on purpose.** Each app spans two devices, and they
/// cut over one at a time. If reads were primary-only, a migrated desktop
/// would never see an un-migrated phone's writes while still mirroring its
/// own back -- silent one-directional convergence, with no error raised.
/// Because `mergeLogs` is commutative and idempotent, a union read costs
/// nothing semantically and makes the cutover order irrelevant.
///
/// Write asymmetry is deliberate too: the primary is authoritative, so a
/// primary failure fails the tick (fail-closed), while a mirror failure is
/// reported through [onMirrorFailure] and otherwise tolerated. Once the
/// mirror is retired, the old backend going away must not break sync.
class MirrorStore implements RemoteStore, BulkMapReader {
  MirrorStore({
    required this.primary,
    required this.mirror,
    this.onMirrorFailure,
  });

  /// The authoritative backend. Its failures fail the tick.
  final RemoteStore primary;

  /// The backup backend. Kept in step, but never allowed to fail a tick.
  final RemoteStore mirror;

  /// Notified when the mirror misbehaves. A silent mirror failure would let
  /// the fallback rot unnoticed until the day it was needed.
  final MirrorFailureHandler? onMirrorFailure;

  @override
  Future<List<String>> listDirectory(String path) async {
    final names = <String>{...await primary.listDirectory(path)};
    await _tryMirror('listDirectory $path', () async {
      names.addAll(await mirror.listDirectory(path));
    });
    return names.toList();
  }

  @override
  Future<String?> getFileText(String path) async {
    final text = await primary.getFileText(path);
    if (text != null) return text;
    // Absent from the primary means "this device has not migrated yet", not
    // "no data" -- so fall through rather than reporting nothing.
    String? fallback;
    await _tryMirror('getFileText $path', () async {
      fallback = await mirror.getFileText(path);
    });
    return fallback;
  }

  @override
  Future<void> putFileText(
    String path,
    String text, {
    required String message,
  }) async {
    await primary.putFileText(path, text, message: message);
    await _tryMirror('putFileText $path', () async {
      await mirror.putFileText(path, text, message: message);
    });
  }

  @override
  Future<void> deleteFile(
    String path, {
    String message = 'crdt_sync: delete',
  }) async {
    await primary.deleteFile(path, message: message);
    await _tryMirror('deleteFile $path', () async {
      await mirror.deleteFile(path, message: message);
    });
  }

  /// Whether the **primary** is reachable.
  ///
  /// Only the primary: a settings "Test connection" button must not report
  /// success because the backend being retired happens to answer.
  @override
  Future<bool> canAccessRemote() => primary.canAccessRemote();

  /// Merges both backends' revision maps, preferring the primary's entry.
  ///
  /// A device that has not migrated publishes revisions only to the mirror;
  /// without this it would look revision-less and be re-downloaded every
  /// tick for the whole trial period.
  @override
  Future<Map<String, String>> getStringMap(String path) async {
    final merged = <String, String>{};
    // Pattern binds rather than `is` promotion: BulkMapReader is not a
    // subtype of RemoteStore, and Dart only promotes to subtypes of the
    // declared type, so the intersection has to be named explicitly.
    await _tryMirror('getStringMap $path', () async {
      if (mirror case final BulkMapReader reader) {
        merged.addAll(await reader.getStringMap(path));
      }
    });
    // Primary applied last so its entries win on conflict.
    if (primary case final BulkMapReader reader) {
      merged.addAll(await reader.getStringMap(path));
    }
    return merged;
  }

  @override
  void close() {
    primary.close();
    mirror.close();
  }

  /// Runs a mirror operation, reporting rather than propagating its failure.
  Future<void> _tryMirror(String operation, Future<void> Function() run) async {
    try {
      await run();
    } on RemoteSyncError catch (error) {
      onMirrorFailure?.call(operation, error);
    }
  }
}
