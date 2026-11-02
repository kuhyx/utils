# google_account_token

Android one-tap Google ID token via `AccountManager`, owned once for every
sync app. The system account chooser, then
`getAuthToken(account, "audience:server:client_id:<WEB client id>")`. The
result is a Google ID token for Firebase `signInWithIdp`: one dialog, no
browser, no `google_sign_in`, no Play Services SDK in the APK. Verified on a
Pixel: aud = the Web client, Firebase accepted it.

Other platforms (web, Linux desktop, iOS) return `null`, so the caller falls
back to its password path.

## Install

```yaml
dependencies:
  google_account_token:
    git:
      url: https://github.com/kuhyx/utils
      ref: google_account_token-v0.1.0
      path: google_account_token
```

Android plugins auto-register: the app's `MainActivity` needs no code.

## API

```dart
import 'package:google_account_token/google_account_token.dart';

if (googleAccountTokenSupported) {
  final idToken = await googleIdToken(serverClientId: kWebClientId);
  // null = cancelled / unsupported / failed (logged); use the password path
}
```

- `googleIdToken({required String serverClientId, String? accountHint})`
  returns the ID token or `null`. `serverClientId` must be the **Web** OAuth
  client id (an Android client id gives `audience mismatch` at Firebase).
  `accountHint` (an email) only preselects a row; the chooser always shows.
- `googleAccountTokenSupported` is true only on Android.
- There is no sign-out: the plugin holds no session. Each call is a fresh
  chooser plus `getAuthToken`; forgetting the account is the app's own
  stored credentials.

Failures are logged (level 900) and returned as `null`; a misconfigured
client id looks the same as "user cancelled" except in the log.

## Development

```bash
flutter test --coverage && scripts/check_coverage.sh coverage/lcov.info 100
flutter analyze
```

The Kotlin side (`android/.../GoogleAccountTokenPlugin.kt`) has no JVM unit
test: utils has no Kotlin test convention and Android unit tests hit the
MockableJarTransform / android-36 / JDK 21 breakage. It was compile-checked
through a throwaway app (`:google_account_token:compileDebugKotlin`).
