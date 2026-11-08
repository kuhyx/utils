# data_transfer_flutter

Shared "export to a JSON file / import from a JSON file" plumbing for kuhy's
Flutter apps. Apps keep their own export CONTENT; this owns the file plumbing
and the envelope.

## Install

```yaml
dependencies:
  data_transfer_flutter:
    git:
      url: https://github.com/kuhyx/utils
      ref: data_transfer_flutter-v0.2.1
      path: data_transfer_flutter
```

## Use

```dart
final saved = await exportJson(fileName: 'x.json', json: envelope);
final map = await pickJson(); // null when cancelled
```

- `exportJson` / `exportJsonText` save to **device storage**: Android and iOS
  use the system "Save as" document picker (`file_picker` `saveFile`, i.e.
  ACTION_CREATE_DOCUMENT), desktop a save dialog (`file_selector`), web a
  browser download. Returns false when cancelled.
- `exportTextFile` does the same for any text (`text/csv`, `text/calendar`).
- `shareJson` is an optional second action (share sheet). It is never the
  only way out: a stock phone's share sheet has no local save target.
- `pickJson` / `pickJsonText` use the system open-document picker.
- `buildEnvelope` / `validateEnvelope` / `parseEnvelope` write and check
  `{format, version, exported_at, ...}`; mismatches throw a typed
  `EnvelopeException` (always a `FormatException`).

Tests fake `DataTransfer.platform` (a `DataTransferPlatform`); restore it in
`tearDown`.
