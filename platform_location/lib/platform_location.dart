/// Android location through the platform `LocationManager`, owned once for
/// every app.
///
/// Why a plugin and not geolocator: geolocator_android links
/// `com.google.android.gms:play-services-location` (and with it
/// play-services-base, -basement and -tasks, all non-free) even with
/// `forceLocationManager: true`. This package talks to AOSP's
/// `LocationManager` through androidx `LocationManagerCompat` only.
///
/// Being a real plugin (not a MainActivity channel), it also registers in
/// background engines such as a flutter_foreground_task service isolate.
/// Everything but [PlatformLocation.requestPermission] works there.
///
/// Tests swap [PlatformLocation.instance] for a fake, the way geolocator's
/// `GeolocatorPlatform.instance` used to be swapped.
library;

import 'package:flutter/services.dart';

/// The method channel `PlatformLocationPlugin.kt` answers on.
const kPlatformLocationChannel = MethodChannel('dev.kuhy/platform_location');

/// The event channel that streams fixes.
const kPlatformLocationFixes = EventChannel('dev.kuhy/platform_location/fixes');

/// Whether the app may read the location.
enum LocationPermissionState {
  /// Fine or coarse location is granted.
  granted,

  /// Not granted; asking again may show the system prompt.
  denied,

  /// Refused for good; only the system settings can change it.
  deniedForever;

  static LocationPermissionState _parse(String? name) =>
      LocationPermissionState.values.firstWhere(
        (s) => s.name == name,
        orElse: () => LocationPermissionState.denied,
      );
}

/// One location fix.
class LocationFix {
  /// Creates a fix.
  const LocationFix({
    required this.time,
    required this.latitude,
    required this.longitude,
    this.altitude = 0,
    this.accuracy = 0,
    this.isMock = false,
  });

  /// Decodes the map the Kotlin side sends.
  factory LocationFix.fromMap(Map<Object?, Object?> map) => LocationFix(
    time: DateTime.fromMillisecondsSinceEpoch(
      (map['time']! as num).toInt(),
      isUtc: true,
    ),
    latitude: (map['latitude']! as num).toDouble(),
    longitude: (map['longitude']! as num).toDouble(),
    altitude: (map['altitude'] as num?)?.toDouble() ?? 0,
    accuracy: (map['accuracy'] as num?)?.toDouble() ?? 0,
    isMock: map['isMock'] as bool? ?? false,
  );

  /// When the fix was taken (UTC).
  final DateTime time;

  /// Degrees north.
  final double latitude;

  /// Degrees east.
  final double longitude;

  /// Metres above the WGS84 ellipsoid; 0 when the provider has none.
  final double altitude;

  /// Horizontal accuracy radius in metres; 0 when unknown.
  final double accuracy;

  /// Whether a mock-location app produced this fix.
  final bool isMock;
}

/// The location API; [instance] is the seam tests replace.
abstract class PlatformLocation {
  /// The active implementation; a test assigns a fake here.
  static PlatformLocation instance = MethodChannelPlatformLocation();

  /// Whether the device's location switch is on.
  Future<bool> isLocationEnabled();

  /// The permission as it stands; never prompts. Reports
  /// [LocationPermissionState.denied], never `deniedForever`: Android only
  /// tells a permanent refusal apart right after a request.
  Future<LocationPermissionState> checkPermission();

  /// Shows the system prompt (needs a foreground Activity). [precise] asks
  /// for fine location as well as coarse.
  Future<LocationPermissionState> requestPermission({bool precise = true});

  /// One fresh fix; throws a [PlatformException] when there is none
  /// (no permission, location off, timeout).
  Future<LocationFix> currentLocation();

  /// Fixes about every [interval], best accuracy, until cancelled.
  Stream<LocationFix> fixes({Duration interval = const Duration(seconds: 2)});
}

/// [PlatformLocation] over [kPlatformLocationChannel].
class MethodChannelPlatformLocation extends PlatformLocation {
  @override
  Future<bool> isLocationEnabled() async =>
      await kPlatformLocationChannel.invokeMethod<bool>('isLocationEnabled') ??
      false;

  @override
  Future<LocationPermissionState> checkPermission() async =>
      LocationPermissionState._parse(
        await kPlatformLocationChannel.invokeMethod<String>('checkPermission'),
      );

  @override
  Future<LocationPermissionState> requestPermission({
    bool precise = true,
  }) async => LocationPermissionState._parse(
    await kPlatformLocationChannel.invokeMethod<String>('requestPermission', {
      'precise': precise,
    }),
  );

  @override
  Future<LocationFix> currentLocation() async {
    final map = await kPlatformLocationChannel
        .invokeMapMethod<Object?, Object?>('currentLocation');
    if (map == null) {
      throw PlatformException(code: 'no_fix', message: 'no location');
    }
    return LocationFix.fromMap(map);
  }

  @override
  Stream<LocationFix> fixes({Duration interval = const Duration(seconds: 2)}) =>
      kPlatformLocationFixes
          .receiveBroadcastStream({'intervalMs': interval.inMilliseconds})
          .map((e) => LocationFix.fromMap(e as Map<Object?, Object?>));
}
