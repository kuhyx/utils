import 'package:crdt_sync_flutter/crdt_sync_flutter.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('generates a uuid on first call and persists it', () async {
    final prefs = await SharedPreferences.getInstance();

    final first = await loadDeviceIdentity(preferences: prefs);

    expect(first.deviceId, isNotEmpty);
    expect(prefs.getString(kNodeIdKey), first.deviceId);
  });

  test('returns the same id on every later call', () async {
    final prefs = await SharedPreferences.getInstance();

    final first = await loadDeviceIdentity(preferences: prefs);
    final second = await loadDeviceIdentity(preferences: prefs);

    // A changing id would push under a new path every launch and re-merge
    // this device's own history as though a peer had written it.
    expect(second.deviceId, first.deviceId);
  });

  test('gives two installs different ids', () async {
    final a = await loadDeviceIdentity(
      preferences: await SharedPreferences.getInstance(),
    );
    SharedPreferences.setMockInitialValues({});
    final b = await loadDeviceIdentity(
      preferences: await SharedPreferences.getInstance(),
    );

    // Two devices sharing an id overwrite each other's pushed file on every
    // tick, which is the whole reason this is a uuid and not a role constant.
    expect(b.deviceId, isNot(a.deviceId));
  });

  test('carries a legacy id so a migrated device knows itself', () async {
    final identity = await loadDeviceIdentity(
      legacyId: 'phone',
      preferences: await SharedPreferences.getInstance(),
    );

    expect(identity.isOwn('phone'), isTrue);
    expect(identity.isOwn(identity.deviceId), isTrue);
    expect(identity.isOwn('some-other-device'), isFalse);
  });

  test('resolves SharedPreferences itself when none is passed', () async {
    // The production call site passes nothing; the mock binding stands in for
    // the real plugin, so the default path is exercised rather than assumed.
    SharedPreferences.setMockInitialValues({kNodeIdKey: 'ambient-uuid'});

    final identity = await loadDeviceIdentity();

    expect(identity.deviceId, 'ambient-uuid');
  });

  test('adopts an id already written by a pre-package app', () async {
    // The key matches what the existing apps wrote, so adopting this package
    // keeps a device's identity instead of making it look brand new.
    SharedPreferences.setMockInitialValues({kNodeIdKey: 'existing-uuid'});

    final identity = await loadDeviceIdentity(
      preferences: await SharedPreferences.getInstance(),
    );

    expect(identity.deviceId, 'existing-uuid');
  });
}
