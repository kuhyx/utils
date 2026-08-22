/// The per-install device id, persisted in `SharedPreferences`.
///
/// Every device that pushes into a namespace needs an id that is its own: it
/// is the directory segment its log is pushed under, the revision key, and
/// the node component of every HLC stamp it writes. Two devices sharing an id
/// overwrite each other's pushed file on every tick, which is why a role
/// constant (`phone`, `pc`) is wrong and a per-install uuid is right.
///
/// Not the keystore: this is an identifier, not a secret, and the keystore is
/// slower and can be cleared independently of app data. `SharedPreferences`
/// shares the app-data lifetime the log itself has.
library;

import 'package:crdt_sync/crdt_sync.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

/// Preferences key holding this install's uuid.
///
/// Named to match what the existing apps already wrote, so an app adopting
/// this package keeps its identity instead of appearing as a new device and
/// re-merging its own history as a stranger's.
const String kNodeIdKey = 'crdt.nodeId';

/// Returns this install's [DeviceIdentity], generating one on first call.
///
/// [legacyId] is the fixed role string an app pushed under before it moved to
/// a persisted uuid. Passing it keeps skip-own-writes correct: stamps already
/// written carry the old id, and a device that does not recognise its former
/// id re-downloads its own pre-migration history as though a peer wrote it.
/// Pass null for a new app, which has no history to be confused by.
Future<DeviceIdentity> loadDeviceIdentity({
  String? legacyId,
  SharedPreferences? preferences,
}) async {
  final prefs = preferences ?? await SharedPreferences.getInstance();
  var nodeId = prefs.getString(kNodeIdKey) ?? '';
  if (nodeId.isEmpty) {
    nodeId = const Uuid().v4();
    await prefs.setString(kNodeIdKey, nodeId);
  }
  return DeviceIdentity(deviceId: nodeId, legacyId: legacyId);
}
