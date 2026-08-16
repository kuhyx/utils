Give dufs-cloud real latency feedback on its slow operations

## findings (4, ranked by value over effort)

1. **No cancel on the unbounded index walk or the ZIP build** — the real
   usability failure, and worth more than any animation.
2. **Slow operations report one static string** — the walk and the zip both know
   real counts and discard them.
3. **No `prefers-reduced-motion` block anywhere in 806 lines of CSS** — a
   straight accessibility gap.
4. **Long-press multi-select has no haptic** — the canonical place for one.

## what

dufs-cloud has genuinely slow operations and tells the user almost nothing while
they run. Verified 2026-08-16:

- The **recursive cloud index walk** lists every directory in the cloud,
  unbounded. Web shows one static string `"Indexing cloud…"`; Flutter shows one
  indeterminate `CircularProgressIndicator`. **No count, no current path, no
  cancel** on either side.
- The **multi-file ZIP build** downloads every selected file's bytes into memory
  and then zips them, with `setBusy('Preparing N item(s)…')` — a single static
  string for the entire operation. Neither `buildSelectionZip` signature even
  accepts a progress callback.
- Web's entire 806-line `index.css` contains **exactly one transition**
  (`.tile-actions { transition: opacity 0.12s }` ~:539-544), zero `@keyframes`,
  and **no `prefers-reduced-motion` block at all**.
- Flutter side has **zero animations and zero haptics** — notably
  `browser_screen.dart` (~:95) enters multi-select on **long-press** with no
  `HapticFeedback.selectionClick()`, the canonical place for one.

This is the article's micro-animation point in its most defensible form: replace
dead latency with honest, informative feedback. Nothing here needs a manufactured
reward — the operations are genuinely slow and the progress is genuinely knowable.

## where

Repo: `~/dufs-cloud`. Web: `web/`. Flutter: `app/` (package `dufs_client`).

**First step — bump both dependencies** to pick up prompt 01's motion tokens:
- `web/package.json`: `"@kuhyx/web-ui": "github:kuhyx/utils#web_ui-v0.3.1&path:/web_ui"`
  → bump to **`web_ui-v0.3.2`** (or whatever tag prompt 01 printed).
  **pnpm only** — npm cannot install a monorepo subdirectory and will lock the repo.
- `app/pubspec.yaml`: bump `design_system` to the tag prompt 01 cut.
  **Prompt 07 must have run first** — it is what adds this dependency at all.

Slow operations (the highest-value targets):
- Index walk — web `web/src/hooks/use-cloud-index.ts` (`walkInto` ~:36-43, root
  walk ~:56-63, `loading` derived ~:113); Flutter
  `app/lib/services/cloud_index.dart` (`buildCloudIndex` ~:25, `_walk` ~:31-41),
  driven by `app/lib/screens/browser_screen.dart` `_ensureIndex()` ~:184-194.
- ZIP build — web `web/src/lib/download.ts` (`gatherFiles` ~:24,
  `buildSelectionZip` ~:37-47, `saveBytes` ~:55; encoder `web/src/lib/zip.ts`
  `zipStore` ~:32), triggered from `web/src/components/gallery.tsx` ~:307;
  Flutter `app/lib/services/download_zip.dart` (`gatherFiles` ~:15,
  `buildSelectionZip` ~:29-37).
- Upload — web `gallery.tsx` ~:186; Flutter
  `app/lib/services/dufs_client.dart` `upload()` ~:73-81 (a plain `_http.put`
  with the full body — **not** a `StreamedRequest`, so byte progress is not
  currently observable), called from `browser_screen.dart` ~:339.
- Bulk mutations, all single static strings in `gallery.tsx`: move ~:211/:271,
  delete ~:229/:290 (the bulk delete loops per item and reports only a final
  failure count), rename ~:243, create dir ~:257.
- Directory listing — web `web/src/hooks/use-listing.ts` ~:31-72; Flutter
  `browser_screen.dart` ~:120/:140/:149/:155.

Other surfaces:
- `web/src/index.css` (806 lines; `.busy` styled ~:87 — static text, no shimmer).
- `web/src/components/filter-bar.tsx` ~:75-83 — the search input fires `onFilter`
  on **every keystroke with no debounce**.
- `web/src/components/gallery.tsx` ~:454 `{loading && <p className="muted">Loading…</p>}`,
  ~:355 the `busy` span; `folder-picker.tsx` ~:97.
- Flutter spinners: `browser_screen.dart` ~:717, ~:732, `RefreshIndicator` ~:748
  (the one built-in motion affordance), plus `text_editor_screen.dart` ~:101/:80,
  `audio_screen.dart` ~:104, `video_screen.dart` ~:169, `pdf_screen.dart` ~:184,
  `app/lib/widgets/folder_picker.dart` ~:92.
- Settings: `app/lib/screens/settings_screen.dart` (93 lines — room for a toggle),
  store `app/lib/services/settings.dart`.

## must

**Step 1 — motion + honest progress (the valuable half).**

- Make the index walk report **real progress**: directories walked, files found,
  and ideally the current path. The walk already knows these numbers — it just
  discards them. Thread a progress callback through `buildCloudIndex`/`walkInto`.
- Make the ZIP build report **per-file progress** (`3 of 47`). Both
  `buildSelectionZip` signatures need a progress callback added; today neither
  accepts one.
- Add a **cancel** to both. A long unbounded operation with no way out is the
  actual usability failure here, and it is more valuable than any animation.
- Add `HapticFeedback.selectionClick()` on the Flutter **long-press to
  multi-select** (`browser_screen.dart` ~:95). No dependency needed
  (`flutter/services.dart`); add `<uses-permission
  android:name="android.permission.VIBRATE"/>` to the manifest if absent.
- Add a `@media (prefers-reduced-motion: reduce)` block to `web/src/index.css`.
  **There is none today** — this is a straight accessibility gap, not a nicety.
  Flutter side: honour `MediaQuery.of(context).disableAnimations`.
- Use the shared motion tokens for any transition you add. Replace the inline
  `0.12s` at `index.css` ~:539-544 with the token while you are there.
- Debounce the search input (`filter-bar.tsx` ~:75-83). Firing on every keystroke
  over a large index is the cause of jank, and no animation fixes that.

**Step 2 — sound (separate, independently revertable).**

- A completion cue for long operations only (index built, ZIP ready, upload
  finished) — **not** for navigation or selection. A file manager that chirps on
  every click is intolerable.
- Sound ships **on**, with an opt-out toggle in
  `app/lib/screens/settings_screen.dart` backed by `app/lib/services/settings.dart`,
  and an equivalent on web.
- Consider suppressing the cue when the operation finishes in under ~2s — a
  completion sound for something that felt instant is noise.

**Both steps:**

- must not: **fake progress.** No indeterminate bar dressed up as determinate, no
  bar that advances on a timer, no "estimated" percentage that is really elapsed
  time. If a total is unknown, show the count that *is* known ("47 files found")
  rather than a fabricated fraction. This is the project's first test and the
  easiest place in the fleet to violate it.
- must not: add a variable/random reward. There is no real pool here; any
  variance would be manufactured.
- must not: change what the index actually contains, or filter/sort semantics
  (`web/src/lib/filter-sort.ts`, `app/lib/util/filter_sort.dart` mirror each
  other — a change to one desyncs the port).
- must not: use npm in `web/`. **pnpm only.**
- must not: let web and Flutter drift further apart. If you add a progress
  callback on one side, add the equivalent on the other, or state explicitly in
  the summary why not.

- optional: skeleton screens for the directory listing instead of "Loading…".
  Genuinely useful for perceived latency, but lower value than cancel + real
  counts. Do it only after step 1 lands.

## done

1. Starting a cloud index shows a live, **true** count and can be cancelled — on
   both web and Flutter.
2. A multi-file ZIP shows per-file progress and can be cancelled.
3. `web/src/index.css` has a `prefers-reduced-motion` block; with the OS setting
   on, transitions are suppressed.
4. Long-press multi-select produces a haptic on the phone.
5. `cd ~/dufs-cloud/web && pnpm install && pnpm build && pnpm test` passes
   (use the repo's actual script names).
6. `cd ~/dufs-cloud/app && flutter analyze && flutter test` clean.
7. No fabricated progress value anywhere in the diff.

## verify

**Both surfaces — this repo has two and they drift.**

Web: run the dev server, open it in a real browser, and index a directory large
enough to take several seconds. Confirm the count moves, the cancel works, and
the numbers are real (cross-check the final count against the actual file count).
A jsdom test cannot verify this — it has no layout and no perceived latency.

Flutter, on the phone:
```
adb devices
cd ~/dufs-cloud/app
flutter build apk --release
adb install -r build/app/outputs/flutter-apk/app-release.apk
```
Never `adb uninstall`/`pm clear` — the app holds a stored credential.

Then trigger a real index build and a real multi-file ZIP on the device and
report what you saw. State the haptic as a physical observation.

## read first

- `web/src/hooks/use-cloud-index.ts` and `app/lib/services/cloud_index.dart` —
  read both before changing either; they mirror each other deliberately.
- `web/src/lib/download.ts` and `app/lib/services/download_zip.dart` — same.
- `web/src/components/gallery.tsx` — the `setBusy` call sites; they are the
  inventory of every operation currently reduced to one static string.
- `~/dufs-cloud/DESIGN_AUDIT_TODO.md` — prior findings for this repo.
- `~/utils/unified-design-system/motion.md` — vocabulary from prompt 01.

## context you would otherwise rediscover

- **Prompt 07 must have run first.** Until it does, `app/` has no
  `design_system` dependency and hand-restates the palette in
  `app/lib/ui/theme.dart`.
- Web tokens come from `@kuhyx/web-ui` imported in `web/src/main.tsx`;
  `web/src/index.css` declares only `--overlay`. New tokens arrive **only** after
  the tag bump — this is the step that is easy to forget and silently produces
  "the variable doesn't exist".
- `upload()` uses a non-streaming `_http.put`, so real byte-level upload progress
  needs a `StreamedRequest` refactor. That may be more than this prompt wants —
  if you skip it, say so explicitly and report per-**file** progress instead of
  per-byte rather than faking a byte percentage.
- Media playback (`web/src/hooks/use-dash-player.ts`, `web/src/lib/dash-buffer.ts`,
  `app/lib/services/app_player.dart`) has its own buffering states. Out of scope
  unless trivially adjacent.
