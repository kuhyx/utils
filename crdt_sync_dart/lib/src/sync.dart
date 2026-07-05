import 'github_client.dart';
import 'log.dart';
import 'record.dart';

const _defaultFilename = 'log.json';

/// Runs one full sync tick: pull every other device's log, merge, push.
///
/// Pulls from `<pathPrefix>/<other-device-id>/<filename>` for every device
/// directory GitHub reports under [pathPrefix], merges each into
/// [localLog] with [mergeLogs], then pushes this device's own merged result
/// to `<pathPrefix>/<deviceId>/<filename>`.
///
/// [encode] serializes a merged log for pushing. [decode] parses a remote
/// device's pushed text back into a log; throwing [FormatException] is
/// treated as a corrupt/unparsable push, and that device is skipped for
/// this tick rather than aborting the whole sync.
Future<Log> syncLog({
  required GitHubClient client,
  required String deviceId,
  required String pathPrefix,
  required Log localLog,
  required String Function(Log log) encode,
  required Log Function(String text) decode,
  String filename = _defaultFilename,
  String commitMessage = 'crdt_sync: update log',
}) async {
  var mergedLog = Map<String, Record>.from(localLog);
  for (final otherDeviceId in await client.listDirectory(pathPrefix)) {
    if (otherDeviceId == deviceId) continue;
    final text = await client.getFileText(
      '$pathPrefix/$otherDeviceId/$filename',
    );
    if (text == null) continue;
    try {
      mergedLog = mergeLogs(mergedLog, decode(text));
    } on FormatException {
      continue;
    }
  }

  await client.putFileText(
    '$pathPrefix/$deviceId/$filename',
    encode(mergedLog),
    message: commitMessage,
  );
  return mergedLog;
}
