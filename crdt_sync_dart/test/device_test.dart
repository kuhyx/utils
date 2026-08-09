import 'package:crdt_sync/crdt_sync.dart';
import 'package:test/test.dart';

void main() {
  group('DeviceIdentity', () {
    test('ownIds includes both ids while migrating', () {
      const identity = DeviceIdentity(deviceId: 'new-uuid', legacyId: 'phone');

      expect(identity.ownIds, {'new-uuid', 'phone'});
    });

    test('ownIds is just the uuid once the old path is reclaimed', () {
      const identity = DeviceIdentity(deviceId: 'new-uuid');

      expect(identity.ownIds, {'new-uuid'});
    });

    test('isOwn matches either id, and nothing else', () {
      const identity = DeviceIdentity(deviceId: 'new-uuid', legacyId: 'phone');

      expect(identity.isOwn('new-uuid'), isTrue);
      expect(identity.isOwn('phone'), isTrue);
      expect(identity.isOwn('pc'), isFalse);
    });

    test('value equality covers both fields', () {
      const a = DeviceIdentity(deviceId: 'u', legacyId: 'phone');
      const b = DeviceIdentity(deviceId: 'u', legacyId: 'phone');
      const differentLegacy = DeviceIdentity(deviceId: 'u', legacyId: 'pc');
      const noLegacy = DeviceIdentity(deviceId: 'u');

      expect(a, equals(b));
      expect(a.hashCode, equals(b.hashCode));
      expect(a, isNot(equals(differentLegacy)));
      expect(a, isNot(equals(noLegacy)));
      expect(a, isNot(equals(Object())));
    });

    test('toString names both ids', () {
      const identity = DeviceIdentity(deviceId: 'u', legacyId: 'phone');

      expect(identity.toString(), contains('u'));
      expect(identity.toString(), contains('phone'));
    });
  });
}
