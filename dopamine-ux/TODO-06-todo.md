Adopt the motion tokens in todo, and make capture feel immediate

## findings (3, ranked by value over effort)

1. **Capture gives no confirmation** — a successful capture is indistinguishable
   from a no-op unless you go looking for the note.
2. **Zero motion, zero haptics** — despite being the only app already wired to
   the shared package, so adoption here is cheapest.
3. **The pinned `design_system` tag predates the motion tokens** — nothing
   compiles until the ref is bumped. Easy to forget, fatal if skipped.

## what

`todo` is the only app in kuhy's fleet already wired to the shared
`design_system` package — it has **deliberately no local `theme.dart`** (the
pubspec comment says so: nothing to drift from the frozen table). That makes it
the cheapest place to adopt the motion tokens added by prompt 01, and the
reference implementation the other apps get compared against.

Today it has **zero motion and zero haptics**. Verified 2026-08-16: no
`Animated*`, no `AnimationController`, no `HapticFeedback`, no audio. Its only
progress UI is the note-editor wizard bar. Capturing a note — the app's whole
purpose, and the thing that has to feel frictionless enough to actually do —
gives nothing back beyond a toast on error.

Per kuhy's rule for this project: **reward the capture, never the completion
count.** A todo app that celebrates finishing things teaches you to log easy
things; one that celebrates *capturing* keeps the backlog honest.

## where

Repo: `~/todo`.

**First step — bump the dependency.** `pubspec.yaml` pins `design_system` at git
ref `design_system-v0.1.0`, which predates the motion tokens. Bump it to
**`design_system-v0.2.0`** (cut by prompt 01) or the tag that prompt actually
printed. Without this, `AppDuration` does not exist and nothing else here compiles.

Primary:
- `lib/ui/capture_screen.dart`, `lib/ui/capture_screen_widget.dart`,
  `lib/ui/capture_screen_sync.dart` — the capture path. `showError` ~:76 and
  `showToast` ~:78 in `capture_screen_sync.dart` are the fleet's only uses of the
  shared feedback helpers.
- `lib/ui/capture_app_bar.dart` — progress indicators ~:66, :84.
- `lib/ui/note_editor.dart` — `showError` ~:115.
- `lib/ui/note_editor_step_page.dart` ~:80 — `LinearProgressIndicator(value:
  (index+1)/total)`, the wizard step bar. The one honest progress surface.
- `lib/ui/notes_list_screen.dart` — `_searchDebounce = 250ms` ~:45 (**not**
  animation; do not tokenise it).
- `lib/ui/notes_list_navigation.dart`, `lib/ui/settings_screen.dart` (2×),
  `lib/ui/capture_screen.dart` — the `MaterialPageRoute` sites, all using the
  default platform transition.

Settings — **this app has the only working toggle in the fleet; it is the
pattern the other prompts copy**:
- `lib/ui/settings_screen.dart` ~:213-225 — `ValueListenableBuilder<AppSettings>`
  wrapping a `SwitchListTile`; setter ~:111-140 (logs an `AnalyticsEvent`, opens
  a Firebase client, calls `withAdvancedMode`).
- `lib/data/app_settings.dart` — `AppSettings` immutable class,
  `SharedPreferences` keys ~:38-39, `load()` ~:42, `withAdvancedMode` ~:60,
  `reconcileWithRemote` ~:98, `adopt` ~:132 (last-writer-wins cross-device sync
  via `settings/advancedMode` ~:20). Held app-wide as a `ValueNotifier`.

Theme: no local file. `lib/main.dart` ~:4 imports `design_system`; ~:60-61 wires
`theme: buildLightTheme(), darkTheme: buildDarkTheme()`. Source of truth is
`~/utils/design_system/lib/src/theme.dart`.

## must

**Step 1 — motion + haptics (no new dependency).**

- Bump `design_system` to the new tag **first**, and confirm `AppDuration` /
  `AppCurve` resolve before writing any other code.
- Add `HapticFeedback.selectionClick()` (or the token vocabulary's "confirm" cue)
  on **successful note capture**. `HapticFeedback` comes from
  `package:flutter/services.dart` — no pubspec change. Add
  `<uses-permission android:name="android.permission.VIBRATE"/>` to
  `android/app/src/main/AndroidManifest.xml`; it is absent today.
- Fire the haptic **on the tap**, not after the Firebase sync returns. The whole
  point of the micro-animation idea is that immediate feedback removes the
  perceived latency; a cue gated on a network round-trip reintroduces it.
- Give the capture a visible confirmation — currently a successful capture is
  indistinguishable from a no-op unless you go looking.
- Animate the wizard `LinearProgressIndicator` between steps rather than jumping.
- Apply the shared page-transition/motion tokens to the `MaterialPageRoute` sites
  so navigation matches the rest of the system.
- Honour `MediaQuery.of(context).disableAnimations`: durations collapse to zero,
  haptics still fire.

**Step 2 — sound (separate, independently revertable).**

- Add an audio dependency and an `assets:` block to `pubspec.yaml` (neither
  exists) plus a short capture-confirm cue.
- Sound ships **on**, with an opt-out `SwitchListTile` — copy the
  `advancedMode` pattern verbatim (widget ~:213-225, setter ~:111-140, field in
  `app_settings.dart`). It is the fleet's proven toggle; do not invent a new one.
- Consider whether the sound preference should sync across devices like
  `advancedMode` does, or stay local. Local is the safer default — a per-device
  audio choice is usually what people mean.

**Both steps:**

- must not: reward **completing** a todo more than capturing one. No streak on
  completions, no counter that makes finishing feel better than recording. The
  backlog is only useful if capture stays frictionless and honest.
- must not: add a variable/random reward to capture. There is no real pool to
  draw from here, so any variance would be manufactured — which fails the
  project's second test.
- must not: fabricate progress. The wizard bar's `(index+1)/total` is true; keep
  it that way.
- must not: hand-copy token values into a local `theme.dart`. This app
  deliberately has none — that is a feature, and the pubspec comment says so.
- must not: add `# noqa`-equivalents or suppress analyzer warnings.

- optional: animate the notes-list reordering/filtering, if it falls out cheaply
  from the shared tokens.

## done

1. `pubspec.yaml` references the new `design_system` tag and `flutter pub get`
   resolves it.
2. Capturing a note produces a haptic within ~50ms of the tap and a visible
   confirmation.
3. Wizard step transitions and page navigation use shared motion tokens; no
   inline `Duration` remains for animation purposes (the 250ms search debounce
   and 5s auto-sync debounce stay as they are — they are not motion).
4. `cd ~/todo && flutter analyze` is clean.
5. `cd ~/todo && flutter test` passes.
6. With OS "remove animations" enabled, the app works and durations are zero.
7. Step 2: the sound toggle flips, persists across restart, and silences the cue.

## verify

**On the phone — todo is mobile-primary.**

```
adb devices                      # confirm 23181JEGR08034
cd ~/todo
flutter build apk --release
adb install -r build/app/outputs/flutter-apk/app-release.apk
```

Never `flutter install`, never `adb uninstall`, never `pm clear` — those wipe
real notes. `adb install -r` preserves them.

Then capture a real note on the device and report what the phone did. A haptic is
a physical outcome: say what you felt, do not infer it from code. Also step
through the note-editor wizard to confirm the progress bar animates.

If the app also has a desktop/web surface deployed under `/opt/`, note that it
can go stale independently — but this prompt's done-condition is the phone.

## read first

- `lib/ui/settings_screen.dart` ~:213-225 and `lib/data/app_settings.dart` — the
  toggle pattern, in full, before writing the sound switch.
- `lib/ui/capture_screen_sync.dart` ~:76-78 — how `showToast`/`showError` are
  used today; the shared helpers live in
  `~/utils/design_system/lib/src/feedback.dart`.
- `~/utils/design_system/lib/src/feedback.dart` — `showToast`/`showError`, `_show`
  ~:50. `confirm.dart` beside it **already imports `flutter/services.dart`**, so
  if prompt 01 added a shared haptic helper it lives near here.
- `~/utils/unified-design-system/motion.md` — the vocabulary from prompt 01.
  **Prompt 01 must have run first, and its tag must be cut.**
- `pubspec.yaml` — read the comment explaining why there is no local theme.

## context you would otherwise rediscover

- `showToast` and `showError` already carry fixed dwell times in the shared
  package (`_toastDuration = 3s`, `_errorDuration = 5s`,
  `feedback.dart` ~:14, :18). Those are **not** motion tokens; leave them.
- This is the **only** app on `design_system`. diet-guard, workout_app and
  wake_alarm hand-transcribe tokens into local theme files, so a widget copied
  from this app into one of those will not compile unmodified.
- The app has no streaks, no rings, no history charts, and no completion counts
  today. That is a deliberate starting point for this prompt, not an oversight to
  fix wholesale.
- Settings sync cross-device last-writer-wins through Firebase
  (`settings/advancedMode`). If you add a synced preference, follow
  `reconcileWithRemote`/`adopt`; if local-only, skip that path entirely.

REMOVE ME AFTER FINISH
