Close the feedback asymmetry in workout_app

## findings (4, ranked by value over effort)

1. **Finishing a workout gets no cue** — while the rest timer gets sound *and*
   an 800ms vibration. The app celebrates waiting and ignores achieving. All
   infrastructure is already present; only the call is missing.
2. **Set completion has no haptic** — the app's most repeated action, silent.
3. **The fleet's only animation is an inline magic number** —
   `Duration(milliseconds: 200)` in `exercise_tile_rows.dart`.
4. **No sound opt-out exists** — the SQLite settings table is ready, but no
   public accessor and no `SwitchListTile` anywhere. Step 2 only.

## what

workout_app is the only app in kuhy's fleet that can already play a sound and
vibrate — and it spends that capability on the wrong moment. Verified 2026-08-16:

- **Rest-timer expiry** gets a full cue: `_playBreakEndCue()` in
  `lib/screens/workout_screen_session.dart` (~:128-145) plays
  `assets/sounds/break_end.mp3` and fires `Vibration.vibrate(duration: 800)`.
- **Finishing an entire workout** gets nothing. `_persistFinishedWorkout()` in
  `lib/screens/workout_screen_finish.dart` (~:99-108) ends by showing
  `WorkoutSummaryDialog` with no sound, no haptic, no animation.
- **Completing a set** — the core repeated action of the whole app — gets no
  haptic either. The `GestureDetector` at `lib/widgets/exercise_tile_rows.dart`
  (~:145) toggles state silently.

So the app celebrates *waiting* and ignores *achieving*. Fix the asymmetry: the
moments worth reinforcing are completing a set and finishing a workout.

This app also contains the fleet's **only animation** — a lone
`AnimatedContainer(duration: Duration(milliseconds: 200))` at
`exercise_tile_rows.dart` ~:146-147, with an inline magic number. Replace that
number with a motion token while you are in the file.

## where

Repo: `~/screen-locker`. App: `~/screen-locker/stronglift_replacement/workout_app`
(a Flutter app nested inside the screen-locker repo; that directory contains **no
Python** — only the app and two design docs).

Primary:
- `lib/widgets/exercise_tile_rows.dart` — set-completion `GestureDetector` ~:145,
  the `AnimatedContainer` ~:146-147.
- `lib/screens/workout_screen_finish.dart` — `_persistFinishedWorkout()` ~:99-108.
- `lib/widgets/workout_summary_dialog.dart` — `WorkoutSummaryDialog` ~:10.
- `lib/screens/workout_screen_session.dart` — `_playBreakEndCue()` ~:128-145, the
  existing cue to model the new ones on. Note its `.catchError` only
  `debugPrint`s (~:131-137).
- `lib/screens/workout_screen.dart` — `_audio = AudioPlayer()` ~:78, `vibration`
  import ~:9.
- `lib/widgets/rep_circle.dart` — `RepCircle` ~:34, per-set completion indicator.

Progress/history surfaces (already rich; animate rather than rebuild):
- `lib/screens/history_screen_charts.dart` — `_ProgressStatsCard` ~:71,
  **`_StreakRow` ~:139**, `_WeightChart` ~:192.
- `lib/screens/history_screen_painter.dart` — `_ChartPainter` ~:9, `paint()` ~:46,
  `shouldRepaint` ~:121 (static; no animation today).
- Streak data: `successStreak`/`failStreak` on `ExerciseState`
  (`lib/services/storage_service.dart` ~:42-46).

Settings (for the sound opt-out):
- `lib/screens/settings_screen.dart` — `build()` ~:166, `ListView` ~:174-208.
  Parts: `settings_screen_rows.dart`, `settings_screen_sections.dart`,
  `settings_screen_exercise_sections.dart`, `settings_screen_thresholds.dart`,
  `settings_screen_widget.dart`, `settings_screen_actions.dart`.
  **No `SwitchListTile` exists** — model a new section on `_SyncSection`
  (`settings_screen_sections.dart` ~:14) or `_OfflineBackupSection`.
- Store: **SQLite**, not SharedPreferences. There is a ready-made key/value table
  — schema `lib/services/storage_service_schema.dart` ~:34-36
  (`CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)`, migration
  ~:64-65), accessors `lib/services/storage_service.dart` ~:122-137
  (`_getSetting`/`_setSetting`, both **private** — add a public typed wrapper like
  the existing `setLastWorkoutType`). Already backed up/restored via
  `lib/services/storage_service_backup.dart` ~:23, :43, :156-163.

Theme: `lib/ui/theme.dart` — local hand-copy, **no `design_system` dependency**
(`buildAppTheme()` ~:12, `AppStatusColors` ~:76, `AppSpacing` ~:111,
`AppRadius` ~:133, `AppTextSize`). Wired at `lib/main.dart` ~:115.

## must

**Step 1 — motion + haptics (no new dependency).**

- Add `HapticFeedback.selectionClick()` on **set completion** — the tap at
  `exercise_tile_rows.dart` ~:145. This is the app's most repeated action; it
  should feel like flipping a physical switch. Fire on tap, not after the write.
- Add a completion cue when a **workout finishes** — haptic plus a visible
  arrival for `WorkoutSummaryDialog`, rather than it appearing instantly.
- Replace the inline `Duration(milliseconds: 200)` at ~:146-147 with the motion
  token from prompt 01, transcribed into `lib/ui/theme.dart`.
- Animate the streak/stat numbers on the history screen to their new values
  instead of snapping. `_ChartPainter.shouldRepaint` currently returns a static
  result — leave the chart itself alone unless animating it is cheap.
- Honour `MediaQuery.of(context).disableAnimations` — durations collapse to zero;
  haptics and sound still fire.
- `VIBRATE` is already granted (`android/app/src/main/AndroidManifest.xml` ~:10)
  and `vibration: ^3.1.0` is already a dependency. Prefer `HapticFeedback` from
  `flutter/services.dart` for short UI taps and reserve the `vibration` package
  for the long timed buzz it already does well.

**Step 2 — sound (separate, independently revertable).**

- Add a finish-workout cue asset alongside `assets/sounds/break_end.mp3`
  (declared at `pubspec.yaml` ~:52-53 — **this is the fleet's only `assets:`
  block**, so you are adding a file, not the block).
- Sound ships **on**, with an opt-out. Add a public
  `getSoundEnabled()`/`setSoundEnabled(bool)` on `StorageService` wrapping
  `_getSetting`/`_setSetting` (store `'true'`/`'false'`), then a settings section
  with a `SwitchListTile`.
- The toggle must silence the **new** cues and the existing break-end cue alike —
  one switch, not two behaviours.

**Both steps:**

- must not: **reward the weight or rep number.** The cue fires on *logging a set*
  and *finishing a workout*, not on hitting a PB or beating last week. Rewarding
  the number pushes toward misreporting; rewarding the record keeps the data
  honest. A deloaded set gets the same confirmation as a PB.
- must not: fabricate the streak. `successStreak`/`failStreak` count real
  outcomes; display them as they are.
- must not: add a cue to *deleting* a set or workout.
- must not: silently swallow an audio error. The existing `.catchError` →
  `debugPrint` at ~:131-137 is the local precedent; do not make it quieter.
- must not: break the **100% coverage gate** — new public methods on
  `StorageService` need tests. See the comments at
  `settings_screen_sections.dart` ~:1-11.
- must not: exceed the **250-line cap** on any file.

- optional: a subtle near-miss cue on the history screen when a streak is one
  workout short of a milestone — legitimate only because the number is true.

## done

1. Completing a set produces an immediate haptic on the phone.
2. Finishing a workout produces a haptic and a visible dialog arrival; step 2
   adds a sound.
3. No inline animation duration remains in `exercise_tile_rows.dart`.
4. `cd ~/screen-locker/stronglift_replacement/workout_app && flutter analyze` clean.
5. `flutter test` passes **and coverage stays at 100%**.
6. With OS "remove animations" on, the app works and durations are zero.
7. Step 2: the settings toggle flips, persists across restart, and silences both
   the new cues and the existing break-end cue.

## verify

**On the phone.**

```
adb devices                      # confirm 23181JEGR08034
cd ~/screen-locker/stronglift_replacement/workout_app
flutter build apk --release
adb install -r build/app/outputs/flutter-apk/app-release.apk
```

Never `flutter install`, never `adb uninstall`, never `pm clear` — those wipe the
SQLite workout history. `adb install -r` preserves it.

Then run a real set on the device: tap a set complete, finish a workout, and
report what the phone actually did. Haptics and sound are physical outcomes —
state what you felt and heard; do not infer them from the code.

## read first

- `lib/screens/workout_screen_session.dart` ~:128-145 — `_playBreakEndCue()`, the
  working cue. Your new cues should look like it.
- `lib/widgets/exercise_tile_rows.dart` — the set-completion tap and the fleet's
  only `AnimatedContainer`.
- `lib/services/storage_service.dart` ~:122-137 — `_getSetting`/`_setSetting`, and
  `setLastWorkoutType` as the public-wrapper pattern.
- `lib/screens/settings_screen_sections.dart` ~:1-11 — the coverage/line-cap
  comments, and `_SyncSection` as the section pattern.
- `~/utils/unified-design-system/motion.md` — motion/haptic vocabulary from
  prompt 01. **Prompt 01 must have run first.**

## context you would otherwise rediscover

- This app has **no `design_system` dependency**; `lib/ui/theme.dart` is a
  hand-transcription of the shared tokens. Motion tokens must be transcribed
  there, matching the existing convention. Do not add the dependency here.
- `shared_preferences` **is** a dependency but is used only for the device id
  (`lib/services/sync_device_id.dart` ~:37-38). Settings go in SQLite.
- Non-motion `Duration`s that are **not** animation and must not be touched:
  rest tickers (`workout_screen.dart` ~:91, `workout_screen_breaks.dart` ~:20,
  `workout_screen_session.dart` ~:37 — 1s), settings debounces
  (`settings_screen.dart` ~:140, :148 — 600ms), `main.dart` ~:56 (20s).
- The app syncs to the screen-locker Python side, which treats
  `screen_locker/workout_log.json` as the single source of truth. **Do not change
  what counts as a workout** — enforcement depends on it, and it is out of scope.
- The repo enforces a 250-line file cap and bans `# noqa`; ruff runs
  `select = ["ALL"]` on the Python side.
