/// GitHub OAuth **Device Flow** for kuhy's Flutter apps: the auth client and
/// the modal that drives it.
///
/// Four apps (todo, home_inventory, diet-guard, wake-alarm) each carried a
/// copy of both halves — the todo and home_inventory clients were
/// byte-identical, as were the diet-guard and wake-alarm dialogs. This
/// package is that shared copy.
///
/// Device flow needs only a public `client_id` (no client secret), which is
/// what makes it safe for a distributed app; the resulting access token is
/// then used exactly like a PAT.
///
/// Deliberately **not** part of `sync_settings_ui`: that package is
/// Firebase-only by an explicit 2026-08-12 decision, and folding a GitHub
/// flow into it would reverse that. The GitHub mirror in these apps is
/// legacy-but-load-bearing code, so it gets its own home rather than being
/// merged into the Firebase path or deleted.
library;

export 'src/device_auth.dart'
    show DeviceAuthException, DeviceCodeResponse, GitHubDeviceAuth;
export 'src/device_code_dialog.dart' show DeviceCodeDialog;
