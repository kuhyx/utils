/// This device's stable sync identity.
library;

/// This device's current sync id, plus the id it used to push under before.
///
/// Every device that pushes into a namespace needs an id that is *its own*:
/// it is the directory segment its log is pushed under
/// (`<pathPrefix>/<deviceId>/<filename>`), the revision key, and the node
/// component baked into every HLC stamp it writes (`<iso>-<counter>-<id>`).
/// Two devices sharing an id overwrite each other's pushed file on every
/// tick, so the id must be per-*install*, not per-role.
///
/// A migration from a role constant (`phone`, `pc`, `desktop`) to a persisted
/// uuid cannot rewrite history: stamps already written keep the old id, and
/// the old path still holds the log pushed under it. So a device that has
/// just switched ids must still recognise its *former* id as itself -- which
/// is what [legacyId] carries, and why [ownIds] is a set. Skip-own-writes has
/// to test membership of that set rather than equality with one id, or the
/// device re-downloads and re-merges its own pre-migration history as though
/// a peer had written it.
class DeviceIdentity {
  /// Creates an identity for [deviceId], optionally carrying a [legacyId].
  const DeviceIdentity({required this.deviceId, this.legacyId});

  /// The id to push, stamp and key revisions under from now on.
  final String deviceId;

  /// The id this device pushed under before migrating to a persisted uuid.
  ///
  /// Null once the old path has been reclaimed.
  final String? legacyId;

  /// Every id that means "this device", for skip-own-writes checks.
  Set<String> get ownIds => {deviceId, ?legacyId};

  /// Whether [otherDeviceId] is one of this device's own ids.
  bool isOwn(String otherDeviceId) => ownIds.contains(otherDeviceId);

  @override
  bool operator ==(Object other) =>
      other is DeviceIdentity &&
      other.deviceId == deviceId &&
      other.legacyId == legacyId;

  @override
  int get hashCode => Object.hash(deviceId, legacyId);

  @override
  String toString() =>
      'DeviceIdentity(deviceId: $deviceId, legacyId: $legacyId)';
}
