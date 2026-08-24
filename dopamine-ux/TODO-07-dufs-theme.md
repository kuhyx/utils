Wire dufs-cloud's Flutter app to the shared design_system

## findings (2, ranked by value over effort)

1. **`app/lib/ui/theme.dart` is a fifth, uncompared palette copy** — hand-copied
   hexes that `palette_check.py` has never seen, so it can drift silently while
   CI stays green.
2. **The web half of the same repo is wired correctly** — which makes the
   Flutter half's divergence an accident, not a decision.

## what

`~/dufs-cloud/app/lib/ui/theme.dart` is a **fifth, uncompared copy of the
palette**. Verified 2026-08-16: the Flutter app has no `design_system`
dependency at all — it hand-restates every hex (`Color(0xFF211D1B) // ink`,
`Color(0xFFB8862E) // accent`, …) with the shared token names appearing only in
comments. `palette_check.py` has never seen this file, so it can drift from the
frozen table silently and CI will stay green.

The web half of the same repo is wired correctly (`@kuhyx/web-ui`), which makes
the Flutter half's divergence an accident rather than a decision.

Fix the root cause: add the dependency, replace the hand-copied hexes with token
references, and delete the duplicate. This must land **before** prompt 08 adds
motion to this app, so that motion tokens arrive through the package instead of
becoming a sixth hand-copy.

## where

Repo: `~/dufs-cloud`. Flutter app: `~/dufs-cloud/app` (package `dufs_client`).

- `app/pubspec.yaml` — current deps: `archive, cupertino_icons, flutter,
  flutter_secure_storage, http, image_picker, media_kit*, path, path_provider,
  share_plus, shared_preferences, webview_flutter, xml`. **No `design_system`.**
- `app/lib/ui/theme.dart` — the hand-copy to eliminate.
- Every file referencing a colour from it — find them with a grep for the theme's
  exported symbols rather than trusting any list here.

Source of truth:
- `~/utils/design_system/lib/src/tokens.dart` — `AppPalette`, `AppSpacing`,
  `AppRadius`, `AppTextSize` (plus `AppDuration`/`AppCurve` if prompt 01 ran).
- `~/utils/design_system/lib/src/theme.dart` — `buildLightTheme()`,
  `buildDarkTheme()`.

Reference implementation: `~/todo` is the only app already on the package. Its
`pubspec.yaml` uses a **git ref** (`design_system-v0.1.0`) and it has
deliberately **no local `theme.dart`**. Copy that shape.

## must

- Add `design_system` to `app/pubspec.yaml` using the **git ref** style matching
  `~/todo` — not a local `path:` dependency. One dependency convention across the
  fleet. Pin the tag prompt 01 cut (`design_system-v0.2.0` or whatever it
  printed); if prompt 01 has not run, pin `design_system-v0.1.0` and let prompt
  08 do the bump.
- Replace every hand-copied hex in `app/lib/ui/theme.dart` with the corresponding
  token reference. **Verify each swap is value-identical before making it** — the
  survey found the values byte-identical today, but confirm rather than assume;
  a silent colour change in a live app is a real regression.
- Delete the duplicated token declarations once nothing references them. If the
  app declares helper classes the shared package lacks, keep only those, and say
  in the session summary which ones survived and why.
- Keep the app's visual output **identical**. This is a pure de-duplication: if
  anything looks different afterwards, a value was wrong and you have found a
  pre-existing drift — report it rather than papering over it.

- must not: change any colour, spacing, radius or type **value**. The shared
  table is a freeze. If a value genuinely disagrees, stop and surface it — that
  is a finding, and kuhy decides which side is canonical.
- must not: add motion/animation here. That is prompt 08. This prompt is
  dependency plumbing only, so that a visual regression has exactly one possible
  cause.
- must not: touch `~/dufs-cloud/web/` — its `@kuhyx/web-ui` wiring is already
  correct.
- must not: leave a partial migration. Either the local theme file is gone (or
  reduced to app-specific extras) and everything resolves through the package, or
  the change is not done. A half-migrated theme is worse than the current state
  because it hides *which* copy is authoritative.

- optional: once migrated, add `app/lib/ui/theme.dart`'s path to the structural
  checker from prompt 02 if that is now meaningful. Probably it is not — after
  this prompt there is nothing left there to compare.

## done

1. `app/pubspec.yaml` declares `design_system` at a git ref; `flutter pub get`
   resolves.
2. No hard-coded palette hex remains in `app/lib/`. A grep for `Color(0xFF` in
   `app/lib/ui/theme.dart` returns nothing (or only app-specific values that are
   not palette tokens — name them if so).
3. `cd ~/dufs-cloud/app && flutter analyze` is clean.
4. `cd ~/dufs-cloud/app && flutter test` passes.
5. The app looks **the same** as before on device — verified by screenshot
   comparison, not by reasoning about the diff.
6. `python3 ~/utils/unified-design-system/scripts/palette_check.py` still exits 0.

## verify

**On the phone**, and with a before/after comparison — a pure refactor is only
verified by showing nothing changed.

```
adb devices
cd ~/dufs-cloud/app
flutter build apk --release
adb install -r build/app/outputs/flutter-apk/app-release.apk
```

Take a screenshot of the browser screen and the settings screen **before**
starting (from the currently installed build) and after, and compare them. Never
`adb uninstall` or `pm clear` — the app holds a stored credential
(`flutter_secure_storage`) and wiping it means re-authenticating.

## read first

- `~/dufs-cloud/app/lib/ui/theme.dart` — in full, before touching anything. The
  comments naming each token are your mapping table.
- `~/todo/pubspec.yaml` — the git-ref dependency line to copy, and the comment
  explaining why no local theme exists.
- `~/utils/design_system/lib/src/tokens.dart` — the canonical names.
- `~/dufs-cloud/DESIGN_AUDIT_TODO.md` — a prior audit of this repo; check whether
  it already records theme findings so you do not contradict it.

## context you would otherwise rediscover

- The web half consumes `@kuhyx/web-ui` at tag **`web_ui-v0.3.1`**, declared in
  `~/dufs-cloud/web/package.json` as
  `"github:kuhyx/utils#web_ui-v0.3.1&path:/web_ui"`. It is correctly wired; the
  only app-local CSS value is `--overlay: rgba(33, 29, 27, 0.82)` in
  `web/src/index.css`. Prompt 08 bumps that tag — not this prompt.
- `@kuhyx/web-ui` is **pnpm-only**; npm cannot install a monorepo subdirectory.
  Irrelevant here (this prompt is Flutter-only) but fatal if you wander into
  `web/`.
- `palette_check.py` compares four sources and has never included this file, so
  "CI is green" told you nothing about it. That is the whole reason this prompt
  exists.
- Three other Flutter apps (diet-guard, workout_app, wake_alarm) have the same
  hand-copy pattern. They are **out of scope** — migrating them is a separate,
  larger job, and doing one app properly is the point here.

REMOVE ME AFTER FINISH
