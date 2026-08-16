Add motion and haptics to the wake-alarm phone app

## findings (2, ranked by value over effort)

1. **Setting an alarm gives no confirmation or haptic** — and since the real
   alarm lives in another app entirely, confirming the handoff is the only
   reassurance this app can offer.
2. **Zero motion, and the thinnest local theme in the fleet** — it lacks
   `AppSpacing`/`AppRadius`/`AppTextSize`, so widgets copied from sibling apps
   will not compile here.

## what

`~/wake-alarm/phone_app` is the smallest surface in this project: 12 Dart files,
a sync companion that sets a time, syncs it, and hands off to the system clock
app. It has **zero motion, zero haptics, zero audio, zero progress feedback** —
verified 2026-08-16. Its settings screen is a 56-line `StatelessWidget` with two
`ListTile`s and no state at all.

Bring it up to the fleet's baseline: a confirmation the alarm was actually set,
motion tokens on its transitions, and a haptic on the one action that matters.

**This app is deliberately last and deliberately small.** It also carries the
project's sharpest hazard — see `must not` about alarm audio.

## where

Repo: `~/wake-alarm`. Flutter app: `~/wake-alarm/phone_app` (**underscore**, not
`phone-app`). The repo root is a Python package; the Flutter app is only the
`phone_app/` subdirectory.

Primary:
- `phone_app/lib/screens/home_screen.dart` — `_setPhoneAlarm()` ~:86-96 builds an
  `AndroidIntent(action: 'android.intent.action.SET_ALARM', arguments: {HOUR,
  MINUTES, SKIP_UI: false, MESSAGE: 'Wake Alarm'})` via `android_intent_plus`.
  The `CircularProgressIndicator` is at ~:189. The only `Duration` in the whole
  app is `.timeout(const Duration(seconds: 3))` ~:95 — **an intent timeout, not
  animation. Do not tokenise it.**
- `phone_app/lib/screens/settings_screen.dart` — 56 lines, `StatelessWidget`,
  `ListView` ~:21-53, `MaterialPageRoute` ~:30, :49.
- `phone_app/lib/services/sync_settings.dart` — holds **only** the GitHub token
  in the keystore (`FlutterSecureStorage`, `_secureTokenKey = 'github_token'`
  ~:31, `load()` ~:36, `save()` ~:61). There is no general app-preferences class.
- `phone_app/lib/ui/theme.dart` — local hand-copy, **no `design_system`
  dependency**. `buildAppTheme()` ~:12, `AppStatusColors` ~:54. ⚠️ Unlike the
  other apps it does **not** declare `AppSpacing`/`AppRadius`/`AppTextSize`, so a
  widget copied from diet-guard or workout_app **will not compile here**. Wired at
  `phone_app/lib/main.dart` ~:18.

## must

**Step 1 — motion + haptics (no new dependency).**

- Add `HapticFeedback.mediumImpact()` when the alarm is successfully set — the
  single most important action in the app. Fire it on the tap, not after the
  intent round-trips. `HapticFeedback` is in `package:flutter/services.dart`; add
  `<uses-permission android:name="android.permission.VIBRATE"/>` to
  `phone_app/android/app/src/main/AndroidManifest.xml` if absent.
- Give setting the alarm a **clear confirmation**: which time was set, and that
  the handoff to the system clock succeeded. Today the user gets a `_status`
  string and a spinner. Since the actual alarm lives in another app, confirming
  the handoff is the only reassurance this app can offer — make it unambiguous.
- Transcribe the motion tokens from prompt 01 into `phone_app/lib/ui/theme.dart`,
  matching the existing hand-copy convention. Add `AppSpacing`/`AppRadius`/
  `AppTextSize` **only if** you need them; otherwise leave the file's shape alone.
- Apply motion tokens to the two `MaterialPageRoute` transitions.
- Honour `MediaQuery.of(context).disableAnimations`.

**Step 2 — sound (optional here; consider skipping).**

- A UI confirmation cue would need an audio dependency, an `assets:` block, a
  settings toggle, **and** a preferences class that does not exist yet (see
  below). For an app whose entire job is to hand off to another app, that is a
  poor value ratio.
- **Recommendation: skip sound in this app** and say so explicitly in the session
  summary. If you do add it, it needs the full opt-out toggle like everywhere
  else — and the toggle work below.
- To add any toggle here you must do three things the other apps do not require:
  (a) convert `SettingsScreen` from `StatelessWidget` to `StatefulWidget`,
  (b) create a preferences class — there is no `AppSettings` equivalent; model it
  on `~/todo/lib/data/app_settings.dart`, and note `shared_preferences: ^2.3.0`
  is **already a dependency**, (c) add the `SwitchListTile` to the `ListView`.

**Both steps:**

- must not: **touch anything under `~/wake-alarm/wake_alarm/`.** That is the
  desktop Python daemon that produces the real alarm noise — sine-tone WAVs via
  `paplay` → `aplay` → `speaker-test` (`_audio.py`, `_play_on_all_sinks` ~:218,
  pcspkr evdev fallback `_beep_pcspkr` ~:81), escalating 440Hz → 1000Hz → loud in
  the loop at `_alarm.py` ~:393-407, with sink volume save/restore in `_sinks.py`.
  **Never route a UI-sound opt-out through any of it.** A toggle that silences a
  wake-up alarm is a bug that makes someone late for work.
- The two systems never share a process, package, or file — `phone_app` has no
  audio engine at all — so a UI sound layer here **structurally cannot** touch
  alarm playback. Keep it that way; do not build a bridge between them.
- must not: change the alarm-setting intent, its arguments, or the 3s timeout.
  Feedback wraps that call; it does not modify it.
- must not: add a streak, a counter, or any reward for setting an alarm. Waking
  up is not a metric this app owns, and rewarding "alarms set" rewards the wrong
  act entirely.
- must not: copy a widget from another app without checking it only uses symbols
  this app's thinner theme actually declares.

## done

1. Setting an alarm produces a haptic and an unambiguous confirmation naming the
   time that was set.
2. Page transitions use the shared motion tokens; no inline animation `Duration`
   remains (the 3s intent timeout stays).
3. `cd ~/wake-alarm/phone_app && flutter analyze` is clean.
4. `cd ~/wake-alarm/phone_app && flutter test` passes.
5. With OS "remove animations" enabled, the app works and durations are zero.
6. `git diff` shows **no changes under `~/wake-alarm/wake_alarm/`**.
7. The summary states whether sound was added or deliberately skipped.

## verify

**On the phone.**

```
adb devices                      # confirm 23181JEGR08034
cd ~/wake-alarm/phone_app
flutter build apk --release
adb install -r build/app/outputs/flutter-apk/app-release.apk
```

Never `flutter install`, never `adb uninstall`, never `pm clear` — the app stores
a GitHub token in the keystore and wiping it means re-authenticating.

Then set a real alarm on the device: confirm the haptic fired (state it as a
physical observation), the confirmation named the right time, and **the system
Clock app actually received the alarm**. The last one is the real test — this
app's job is the handoff, so verify the alarm exists in the Clock app, not just
that this screen said so.

Do **not** test by letting an alarm actually fire unless kuhy asks — that
involves the desktop daemon and real noise.

## read first

- `phone_app/lib/screens/home_screen.dart` — `_setPhoneAlarm()` in full,
  including the timeout and the `_status` string handling.
- `phone_app/lib/ui/theme.dart` — note what it does **not** declare before
  writing any widget.
- `~/todo/lib/data/app_settings.dart` — the preferences-class pattern, only if
  you decide to do step 2.
- `~/utils/unified-design-system/motion.md` — vocabulary from prompt 01.
  **Prompt 01 must have run first.**

## context you would otherwise rediscover

- **The Flutter app produces no audio whatsoever.** No audio package, no
  `assets:` block; `assets/` contains only launcher icons. It fires an Android
  `SET_ALARM` intent and the **system Clock app** rings. The desktop Python
  daemon is an entirely separate program on a different machine.
- The repo root (`~/wake-alarm/wake_alarm/`, `wake_alarm.egg-info`) is the Python
  package. Only `phone_app/` is Flutter.
- This app has **no `design_system` dependency** and the thinnest local theme in
  the fleet. Adding the dependency is out of scope here (see prompt 07 for what
  that migration looks like when done properly).
- No streaks, no charts, no progress, no completion counts exist — and none
  should be added. This is a two-button utility.
