# firebase/

Deployable configuration for the Firebase project backing `crdt_sync` /
`crdt_sync_dart` sync. Language-neutral, so it lives here rather than under
either library.

**This repository is public.** Nothing here names a concrete project, database
URL, account or uid. Those live in a local, `0600` config file — see
[Local configuration](#local-configuration).

## Why Realtime Database, over REST

* **No SDK.** Official FlutterFire has no Linux desktop support, and one
  caller (`wake_alarm`'s PC side) is a dependency-free systemd job. The REST
  endpoints are plain HTTPS and behave identically on Linux, Android and
  headless.
* **No per-operation quota on the Spark (no-cost) plan.** RTDB bills only
  storage and bandwidth, so a misbehaving sync loop cannot exhaust a daily
  budget and silently stop working mid-day. Firestore's 20k-writes/day cap
  would be a second way to hit a wall, for querying this workload never does.
* **Path model matches the existing layout** — `<prefix>/<deviceId>/<file>` —
  so no data remodelling.

Deliberately **not** used: Cloud Storage (requires a linked billing account
since 2026‑02‑03) and Cloud Functions. Avoiding both keeps the project
structurally incapable of generating a bill.

## `database.rules.json`

Scopes the whole database to a single Firebase Auth uid.

`auth != null` alone would **not** be safe: email/password sign-up is open
through the identitytoolkit REST API to anyone holding the Web API key, and
that key ships inside the Android APKs. Pinning the uid means a stranger who
registers an account still reads and writes nothing.

To deploy, substitute the real uid (Firebase console → Authentication → Users
→ User UID) and paste into **Realtime Database → Rules → Publish**.

Verify the rules are live — an unauthenticated request must be refused:

```bash
curl -s "$DATABASE_URL/.json"
# {"error" : "Permission denied"}   <- expected
```

## Local configuration

Everything environment-specific lives in `~/.config/crdt-sync/`, mode `0600`,
outside version control:

| File | Contents |
|---|---|
| `firebase.json` | `apiKey`, `databaseUrl`, `projectId`, `uid`, `email` |
| `password` | the sync account's password, no trailing newline |
| `database.rules.json` | the deployed rules, with the real uid filled in |

The Web API key is **not** a secret — it is a public project identifier that
ships inside client apps. The password and refresh tokens are the real
secrets.

## Credentials at runtime

No service-account key is used anywhere: it would bypass the security rules
entirely and is trivially extractable from an installed APK. Devices sign in
as the single user and hold a refresh token:

* Android — `flutter_secure_storage`
* Linux — `~/.config/<app>/firebase.json`, mode `0600`

ID tokens last about an hour, so the refresh exchange is mandatory rather than
optional — `diet_guard`'s PC timer alone runs 96 times a day.
