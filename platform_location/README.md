# platform_location

Android location through AOSP's `LocationManager` (androidx
`LocationManagerCompat`, Apache-2.0), owned once for every app. It replaces
`geolocator`: `geolocator_android` links
`com.google.android.gms:play-services-location` (plus play-services-base,
-basement and -tasks, all non-free) even with `forceLocationManager: true`.
An APK built with this package has no `com/google/android/gms` classes.

## Install

```yaml
dependencies:
  platform_location:
    git:
      url: https://github.com/kuhyx/utils
      ref: platform_location-v0.1.0
      path: platform_location
```

Android plugins auto-register, in the UI engine and in background engines
(a flutter_foreground_task service isolate) alike. The app declares
`ACCESS_COARSE_LOCATION` and, for GPS precision, `ACCESS_FINE_LOCATION`.

## API

```dart
import 'package:platform_location/platform_location.dart';

final loc = PlatformLocation.instance;
if (!await loc.isLocationEnabled()) { /* switch is off */ }
var perm = await loc.checkPermission();            // never prompts
if (perm != LocationPermissionState.granted) {
  perm = await loc.requestPermission(precise: false); // needs an Activity
}
final fix = await loc.currentLocation();           // throws PlatformException
final sub = loc.fixes(interval: const Duration(seconds: 2)).listen((f) {});
```

- `checkPermission` reports `granted` or `denied`. Android only tells a
  permanent refusal apart right after a request, so `deniedForever` comes
  from `requestPermission` (refused and no rationale to show).
- Provider: GPS when fine location is granted and GPS is on; else the
  platform fused provider (Android 12+, AOSP), else network. No Play
  services fused provider.
- `currentLocation` falls back to the newest last-known fix, then throws
  `no_fix`. Stream errors: `unavailable`, `denied`, `provider_disabled`.
- `LocationFix`: `time` (UTC), `latitude`, `longitude`, `altitude` (0 when
  the provider has none), `accuracy` (m, 0 when unknown), `isMock`.

Tests replace `PlatformLocation.instance` with a fake subclass.
