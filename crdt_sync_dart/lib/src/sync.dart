import 'dart:convert';

import 'package:crypto/crypto.dart';

import 'log.dart';
import 'record.dart';
import 'remote_store.dart';
import 'sync_state.dart';

const _defaultFilename = 'log.json';

String revisionOf(String encodedLog) =>
    sha256.convert(utf8.encode(encodedLog)).toString();

/// Runs one full sync tick: pull every other device's log, merge, push.
///
/// Pulls from `<pathPrefix>/<other-device-id>/<filename>` for every device
/// directory the remote reports under [pathPrefix], merges each into
/// [localLog] with [mergeLogs], then pushes this device's own merged result
/// to `<pathPrefix>/<deviceId>/<filename>`.
///
/// [encode] serializes a merged log for pushing. [decode] parses a remote
/// device's pushed text back into a log; throwing [FormatException] (bad
/// JSON syntax) or [TypeError] (valid JSON, wrong shape -- e.g. a missing
/// or mistyped field during [Record.fromJson]) is treated as a
/// corrupt/unparsable push, and that device is skipped for this tick
/// rather than aborting the whole sync. Mirrors the Python `sync_log`'s
/// `(ValueError, KeyError, TypeError)` catch for the same reason.
///
/// Pass [stateStore] to enable revision tracking, which skips downloading
/// peers that have not changed and skips pushing a log that has not changed.
/// Without it the tick behaves exactly as it always did: fetch everything,
/// push unconditionally.
///
/// Revisions live at `<revsPath>/<deviceId>` -- one small text node per
/// device, each written only by its owner. Deliberately *not* one shared map
/// per namespace: a whole-map write would erase every other device's entry,
/// after which those peers would look permanently unchanged and never be
/// fetched again. Per-device keys make that failure impossible rather than
/// merely avoided.
///
/// Pass [legacyDeviceId] on a device that has migrated from a fixed role id
/// (`phone`, `pc`, `desktop`) to a persisted uuid: the old path is then
/// treated as this device's own rather than as a peer's, so its
/// pre-migration log is not pulled back and re-merged every tick. Pass null
/// once that path has been reclaimed.
Future<Log> syncLog({
  required RemoteStore client,
  required String deviceId,
  required String pathPrefix,
  required Log localLog,
  required String Function(Log log) encode,
  required Log Function(String text) decode,
  String filename = _defaultFilename,
  String commitMessage = 'crdt_sync: update log',
  SyncStateStore? stateStore,
  String? revsPath,
  String? legacyDeviceId,
}) async {
  final revs = revsPath ?? defaultRevsPath(pathPrefix);
  final state = await stateStore?.load() ?? const SyncState();
  final remoteRevs = stateStore == null
      ? const <String, String>{}
      : await _remoteRevs(client, revs);

  // A set rather than one id: a device that has migrated from a role
  // constant to a persisted uuid still owns the log it pushed under the old
  // id. Matching only the current id would pull that file back and re-merge
  // this device's own pre-migration history as though a peer wrote it.
  final ownIds = <String>{deviceId, ?legacyDeviceId};
  var mergedLog = Map<String, Record>.from(localLog);
  final seenRevs = <String, String>{};
  for (final otherDeviceId in await client.listDirectory(pathPrefix)) {
    if (ownIds.contains(otherDeviceId)) continue;
    final remoteRev = remoteRevs[otherDeviceId];
    if (remoteRev != null && remoteRev == state.peerRevs[otherDeviceId]) {
      // Unchanged since we last merged it, and that merge is already part of
      // localLog -- so the (potentially hundreds of KB) download is pure
      // waste. Carry the revision forward so it stays skipped next tick.
      seenRevs[otherDeviceId] = remoteRev;
      continue;
    }
    final text = await client.getFileText(
      '$pathPrefix/$otherDeviceId/$filename',
    );
    if (text == null) continue;
    try {
      mergedLog = mergeLogs(mergedLog, decode(text));
    } on FormatException {
      continue;
    } on TypeError {
      continue;
    }
    // Only remembered once the merge succeeded: a corrupt push must be
    // retried next tick, not marked as seen.
    seenRevs[otherDeviceId] = remoteRev ?? revisionOf(text);
  }

  final encoded = encode(mergedLog);
  final rev = revisionOf(encoded);
  final unchanged = stateStore != null && rev == state.pushedRev;
  if (!unchanged) {
    await client.putFileText(
      '$pathPrefix/$deviceId/$filename',
      encoded,
      message: commitMessage,
    );
    if (stateStore != null) {
      // Published after the log, never before: a peer that cached "seen rev
      // X" against a log it never received would skip it forever.
      await client.putFileText('$revs/$deviceId', rev, message: commitMessage);
    }
  }
  await stateStore?.save(SyncState(pushedRev: rev, peerRevs: seenRevs));
  return mergedLog;
}

/// Where revisions live for a given [pathPrefix]: a `revs` sibling of the
/// device directory, e.g. `diet-guard-sync/devices` -> `diet-guard-sync/revs`
/// and `todo-sync/notes` -> `todo-sync/revs`.
String defaultRevsPath(String pathPrefix) {
  final cut = pathPrefix.lastIndexOf('/');
  return cut < 0 ? '$pathPrefix/revs' : '${pathPrefix.substring(0, cut)}/revs';
}

/// Reads every peer's published revision, cheaply where the backend allows.
///
/// Degrades to an empty map -- meaning "fetch everything", the old behaviour
/// -- on any backend without [BulkMapReader], so correctness never depends on
/// the optimisation being available.
Future<Map<String, String>> _remoteRevs(
  RemoteStore client,
  String revsPath,
) async {
  // A pattern bind rather than `is!` + promotion: BulkMapReader is not a
  // subtype of RemoteStore, and Dart only promotes to subtypes of the
  // declared type -- so the intersection has to be named explicitly.
  if (client case final BulkMapReader reader) {
    return reader.getStringMap(revsPath);
  }
  return const {};
}
