# `github_device_auth`

GitHub OAuth **Device Flow** for kuhy's Flutter apps: the auth client and the
modal that drives it.

Device flow needs only a public `client_id` (no client secret), which is what
makes it safe for a distributed app. The resulting access token is then used
exactly like a PAT.

## Why this is its own package

Four apps each carried a copy of both halves:

| App | Client | Dialog |
| --- | --- | --- |
| todo | `lib/sync/github_device_auth.dart` (154) | `lib/ui/device_code_dialog.dart` (110) |
| home_inventory | `lib/sync/github_device_auth.dart` (154, **byte-identical** to todo's) | inline |
| diet-guard | `app/lib/services/github_device_auth.dart` (175) | inline (~84, **byte-identical** to wake-alarm's) |
| wake-alarm | `phone_app/lib/services/github_device_auth.dart` (166) | inline (~84) |

~650 lines, two pairs of them byte-for-byte identical.

**It is deliberately not part of `sync_settings_ui`.** That package is
Firebase-only by an explicit decision (2026-08-12), recorded with "do not
re-add a GitHub section without kuhy asking again". Folding a GitHub flow into
it would reverse that. The GitHub mirror in these apps is legacy-but-
load-bearing code, so it gets its own home rather than being merged into the
Firebase path — or deleted, which was never authorised.

## Use

```yaml
dependencies:
  github_device_auth:
    git:
      url: https://github.com/kuhyx/utils
      ref: github_device_auth-v0.2.0
      path: github_device_auth
```

```dart
final auth = GitHubDeviceAuth(clientId: '<oauth app client id>');
final device = await auth.requestDeviceCode();
final token = await showDialog<String>(
  context: context,
  builder: (_) => DeviceCodeDialog(device: device, auth: auth),
);
auth.close();
```

## Configurable endpoints (web builds)

`deviceCodeUrl` / `tokenUrl` default to GitHub's own URLs, which is right for
mobile and desktop. A **web** build must point both at a local proxy instead:
GitHub's device-flow endpoints send no CORS headers, so a page cannot call
them at all. diet-guard's desktop web build does exactly that, which is why
this knob exists — it was in diet-guard's local copy and would have been lost
had the package shipped only todo's simpler version.

## One behaviour change from the extracted copies

The dialog now catches `on Object`, not `on Exception`.

An `Error` is not an `Exception` in Dart, so `on Exception` let `ArgumentError`
(notably from URI parsing) escape `_poll()` — leaving the dialog spinning on
"Waiting for authorization…" forever with nothing shown to the user. This is
the same trap that silently killed the Firebase sync tick across these apps in
2026-08. Fixed once here rather than four times. `test/device_code_dialog_test.dart`
pins it with a mock that throws an `Error` rather than an `Exception`.

## Commands

```bash
flutter pub get
flutter test              # 23 tests
flutter test --coverage   # 100% of lines
flutter analyze           # very_good_analysis, clean
```
