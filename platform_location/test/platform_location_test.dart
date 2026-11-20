import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:platform_location/platform_location.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  final calls = <MethodCall>[];
  Object? Function(MethodCall) answer = (_) => null;

  setUp(() {
    calls.clear();
    messenger.setMockMethodCallHandler(kPlatformLocationChannel, (c) async {
      calls.add(c);
      return answer(c);
    });
  });
  tearDown(() {
    messenger
      ..setMockMethodCallHandler(kPlatformLocationChannel, null)
      ..setMockStreamHandler(kPlatformLocationFixes, null);
  });

  final fixMap = <Object?, Object?>{
    'time': 1762689600000,
    'latitude': 52.2297,
    'longitude': 21.0122,
    'altitude': 110.5,
    'accuracy': 4,
    'isMock': true,
  };

  test('the default instance talks over the method channel', () {
    expect(PlatformLocation.instance, isA<MethodChannelPlatformLocation>());
  });

  test('isLocationEnabled reads the switch, null means off', () async {
    final api = MethodChannelPlatformLocation();
    answer = (_) => true;
    expect(await api.isLocationEnabled(), isTrue);
    answer = (_) => null;
    expect(await api.isLocationEnabled(), isFalse);
    expect(calls.first.method, 'isLocationEnabled');
  });

  test('permission names map to states, unknown means denied', () async {
    final api = MethodChannelPlatformLocation();
    for (final state in LocationPermissionState.values) {
      answer = (_) => state.name;
      expect(await api.checkPermission(), state);
    }
    answer = (_) => 'whatever';
    expect(await api.checkPermission(), LocationPermissionState.denied);
    answer = (_) => null;
    expect(await api.checkPermission(), LocationPermissionState.denied);
  });

  test('requestPermission passes precise', () async {
    final api = MethodChannelPlatformLocation();
    answer = (_) => 'deniedForever';
    expect(
      await api.requestPermission(precise: false),
      LocationPermissionState.deniedForever,
    );
    answer = (_) => 'granted';
    expect(await api.requestPermission(), LocationPermissionState.granted);
    expect(calls.map((c) => c.arguments), [
      {'precise': false},
      {'precise': true},
    ]);
  });

  test('currentLocation decodes a fix in UTC', () async {
    answer = (_) => fixMap;
    final fix = await MethodChannelPlatformLocation().currentLocation();
    expect(fix.time, DateTime.utc(2025, 11, 9, 12));
    expect(fix.time.isUtc, isTrue);
    expect((fix.latitude, fix.longitude), (52.2297, 21.0122));
    expect((fix.altitude, fix.accuracy, fix.isMock), (110.5, 4.0, true));
  });

  test('missing optional fields default to 0 / not mocked', () {
    final fix = LocationFix.fromMap({'time': 0, 'latitude': 1, 'longitude': 2});
    expect((fix.altitude, fix.accuracy, fix.isMock), (0.0, 0.0, false));
  });

  test('currentLocation throws when there is no fix', () async {
    final api = MethodChannelPlatformLocation();
    answer = (_) => null;
    await expectLater(
      api.currentLocation(),
      throwsA(isA<PlatformException>().having((e) => e.code, 'code', 'no_fix')),
    );
    answer = (_) => throw PlatformException(code: 'unavailable');
    await expectLater(api.currentLocation(), throwsA(isA<PlatformException>()));
  });

  test('fixes streams decoded fixes with the interval', () async {
    Object? listenArgs;
    messenger.setMockStreamHandler(
      kPlatformLocationFixes,
      MockStreamHandler.inline(
        onListen: (args, sink) {
          listenArgs = args;
          sink
            ..success(fixMap)
            ..success({...fixMap, 'isMock': false})
            ..endOfStream();
        },
      ),
    );
    final fixes = await MethodChannelPlatformLocation()
        .fixes(interval: const Duration(seconds: 3))
        .toList();
    expect(listenArgs, {'intervalMs': 3000});
    expect(fixes.map((f) => f.isMock), [true, false]);
  });
}
