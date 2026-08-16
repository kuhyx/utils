Make logging a meal feel satisfying in diet_guard_app

## findings (4, ranked by value over effort)

1. **`_onLogMeal()` gives zero feedback** — no haptic, no sound, no animation, no
   confirmation. The flagship gap. Fix needs no new dependency.
2. **Streak text is inert** — "Adherence streak: N days" is a plain `Text` that
   blinks to a new value. Real data, no salience.
3. **No VIBRATE permission** — blocks haptics until added to the manifest.
4. **No audio capability at all** — no package, no `assets:` block. Step 2 only.

## what

Logging a meal currently produces **no feedback whatsoever**. `_onLogMeal()` in
`lib/screens/log_meal_screen.dart` writes the meal, syncs it, clears the fields,
and calls `setState(() { _progress = buildTodayProgress(log); })`. The progress
card silently appears. No SnackBar, no haptic, no sound, no animation.

That is the whole problem. In kuhy's words: *"noting what you ate should be
SATISFYING and ADDICTING so you WANT TO ACTUALLY note down what you ate."* The
data quality of the entire app depends on the logging habit surviving the days
you don't feel like it, and right now the act of logging gives nothing back.

Make the moment of logging land: an immediate haptic, a real confirmation, and
the streak/progress reacting visibly rather than blinking into existence.

## where

Repo: `~/diet-guard`. Flutter app: `~/diet-guard/app` (package `diet_guard_app`).

Primary:
- `app/lib/screens/log_meal_screen.dart` — `_onLogMeal()` (line 122-168 as of
  2026-08-16; **grep the symbol, the line will drift**). The `setState` that
  silently swaps in the progress card is at ~:164-166. Card rendered at ~:240.
- `app/lib/widgets/today_progress_card.dart` — `TodayProgress` model (~:15),
  `TodayProgressCard` (~:64). Consumed/budget kcal ~:100, P/C/F macro row ~:122,
  **"Adherence streak: N days"** ~:129-130 — all plain `Text`, no ring, no bar.
- `app/lib/widgets/streak_summary_row.dart` — `StreakSummaryRow`: logging streak,
  adherence streak, YTD tally. Also text-only.
- `app/lib/screens/log_meal_progress.dart` — `buildTodayProgress(DayLog)` (~:18),
  `adherenceStreak(...)` (~:31).

Theme (local hand-copy, **no `design_system` dependency**):
- `app/lib/ui/theme.dart` — `buildAppTheme()` ~:12, `AppStatusColors`
  ThemeExtension ~:89, re-declared `AppSpacing` ~:124, `AppRadius` ~:146,
  `AppTextSize`, plus an `AppWidth` class the shared package does not have.

Settings (for the sound opt-out in step 2):
- `app/lib/screens/settings_screen.dart` — body is a `ListView` inside
  `Center > ConstrainedBox(maxWidth: AppWidth.prose)` at ~:161-165.
  **No `SwitchListTile` exists anywhere in this app** — you are adding the first.
- `app/lib/services/app_settings_service.dart` — the store. **Not
  SharedPreferences**: a singleton over a `DocumentStore` writing JSON to
  `app_settings.json` (~:26). `init()` ~:49, `_load()` ~:95-112, setters funnel
  through `_persist`/`_writeToDisk` ~:147-165 (read the comment at ~:153-155 —
  `_writeToDisk` is the single write path every setter must use).
  `resetForTesting`/`initForTesting` at ~:66/:74.

## must

**Step 1 — motion + haptics (no new dependency; land this first).**

- On successful meal log, fire `HapticFeedback.mediumImpact()` (or the token
  vocabulary's "complete" cue if prompt 01 defined one). `HapticFeedback` comes
  from `package:flutter/services.dart` — **no pubspec change needed**. Add
  `<uses-permission android:name="android.permission.VIBRATE"/>` to
  `app/android/app/src/main/AndroidManifest.xml`; it is currently absent.
- Fire it **immediately on the tap**, before the write/sync completes. The
  article's point about micro-animations is that they replace latency with
  feedback; a haptic that waits for a network round-trip defeats it.
- Animate the progress card's arrival and the numbers' change rather than
  snapping: the kcal figure and the streak count should visibly move to their new
  value. Use the motion tokens from prompt 01.
- Show an explicit confirmation of what was recorded — the user should not have
  to infer success from a card appearing.
- Honour `MediaQuery.of(context).disableAnimations`: collapse durations to zero.
  Haptics still fire (they are not motion).

**Step 2 — sound (separate, independently revertable).**

- Add an audio dependency and an `assets:` block to `app/pubspec.yaml` (neither
  exists today), plus a short confirmation cue asset.
- Sound ships **on**, with an opt-out `SwitchListTile` in `settings_screen.dart`,
  backed by a new bool in `app_settings_service.dart` following the existing
  field pattern: private field + static getter, parsed in `_load()`, written via
  `_writeToDisk`.
- The toggle controls **UI sound only**. Never route notification-channel
  behaviour through it.

**Both steps:**

- must not: **reward the calorie number.** The satisfying moment fires on
  *logging*, not on being under budget. Rewarding a low number teaches the user
  to eat less rather than record honestly, and corrupts the app's own data. A
  meal that blows the budget gets the same confirmation as one that doesn't.
- must not: fabricate or round up any displayed value. The streak counts real
  consecutive days; the progress bar reflects the true ratio. Framing, timing
  and salience are fair game — the numbers are not.
- must not: add a celebratory cue to *deleting* or editing a meal. Only the
  record-creating act gets it.
- must not: touch `~/diet-guard/diet_guard/` (the Python desktop side) — it has
  its own streak logic and is out of scope here.
- optional: a progress ring instead of the plain kcal text. The article's
  near-miss point applies honestly here — a ring at 80% of budget is truthful
  and more motivating than a number. Only if it stays accurate.

## done

1. Logging a meal on the phone produces a haptic within ~50ms of the tap, an
   explicit confirmation, and a visible (not instant) update of the streak/progress.
2. `cd ~/diet-guard/app && flutter analyze` is clean.
3. `cd ~/diet-guard/app && flutter test` passes.
4. With OS "remove animations" enabled, the screen still works and durations are
   zero — verified by toggling it, not by reading the code.
5. Step 2 only: the settings toggle flips, persists across an app restart, and
   silences the cue.

## verify

**On the phone — this app is mobile-primary; desktop is not sufficient.**

```
adb devices                      # confirm 23181JEGR08034 is attached
cd ~/diet-guard/app
flutter build apk --release
adb install -r build/app/outputs/flutter-apk/app-release.apk
```

Never `flutter install`, never `adb uninstall`, never `pm clear` — those wipe
real logged food data. `adb install -r` preserves it.

Then log a real meal on the device and report what you felt and saw. A haptic is
a physical outcome: state what the phone did, do not claim it worked from code.
If `com.kuhy.*` focus-mode kills the app on launch, the app needs a focus
whitelist entry before it can be tested.

## read first

- `app/lib/screens/log_meal_screen.dart` — `_onLogMeal()`. Read the whole method
  before editing; the sync call and the field-clearing both matter for where the
  haptic goes.
- `app/lib/services/app_settings_service.dart` — the `dailyKcalGoal` field
  (~:34/:40) is the pattern to copy for a new bool. Note the `_writeToDisk`
  comment.
- `~/diet-guard/diet_guard/_calendar_view.py` — `streaks_text()` ~:136 and
  `ytd_text()` ~:154. The Dart `streak_summary_row.dart` docstring says it mirrors
  this formatting; keep them consistent if you change wording.
- `~/utils/unified-design-system/motion.md` — the motion/haptic vocabulary from
  prompt 01. **Prompt 01 must have run first.**

## context you would otherwise rediscover

- This app has **no `design_system` dependency** — `app/lib/ui/theme.dart` is a
  hand-transcription of the shared tokens (values are byte-identical, names in
  comments). Motion tokens from prompt 01 must be **transcribed into that local
  theme file**, matching the existing convention. Do not add the dependency here;
  that is a separate, larger refactor.
- Capability baseline, verified 2026-08-16: **no audio package, no `assets:`
  block, no `vibration` package, no VIBRATE permission.** The only existing
  audio-adjacent thing is the `diet_guard_due_slot` notification channel
  (`app/lib/services/notification_backend_io.dart` ~:17-18, :52-55) at
  `Importance.high` with no explicit sound/vibration override — leave it alone.
- The app already computes both a **logging streak** and an **adherence streak**
  (`_daystatus.py:144`/`:153` on the Python side, mirrored in Dart). You are
  making existing true data feel like something, not inventing a new metric.
- diet-guard state lives under XDG (`~/.local/share/diet_guard`), unlike
  screen-locker's in-repo JSON. Tests isolate it via
  `~/diet-guard/diet_guard/tests/conftest.py:97` `_isolate_state`.
