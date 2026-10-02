# flutter-setup

Composite action: Flutter for **gating** CI jobs (analyze, test, web build)
from a slim cached SDK.

```yaml
- uses: kuhyx/utils/flutter-setup@flutter-setup-v1
  with:
    flutter-version: 3.47.6   # same as .fvmrc
    working-directory: app    # where pubspec.lock lives
```

## Why

`subosito/flutter-action` with `cache: true` caches the whole SDK: 1.6 GB,
about 13 s to download and 25 s to extract on every job, *on a hit*. That
alone kept every Flutter job over a minute. This action caches a depth-1
clone of the release tag plus the host and web artifacts: 393 MB
compressed, about a quarter of the restore.

Release APK builds keep `subosito/flutter-action`: they need the Android
artifacts this action deliberately leaves out.
