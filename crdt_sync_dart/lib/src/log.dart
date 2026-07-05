import 'record.dart';

/// A collection of [Record]s keyed by id.
typedef Log = Map<String, Record>;

/// Returns the union of [local] and [remote], merging shared ids.
///
/// Commutative and idempotent: `mergeLogs(a, b) == mergeLogs(b, a)` and
/// `mergeLogs(x, x) == x`, so pull order between devices never matters and a
/// repeated sync tick is a no-op.
Log mergeLogs(Log local, Log remote) {
  final merged = Map<String, Record>.from(local);
  for (final entry in remote.entries) {
    final existing = merged[entry.key];
    merged[entry.key] = existing == null
        ? entry.value
        : mergeRecord(existing, entry.value);
  }
  return merged;
}
