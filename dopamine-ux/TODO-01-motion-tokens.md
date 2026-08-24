Add motion, haptic and sound tokens to the unified design system

## findings (3, ranked by value over effort)

1. **No motion token exists in any stack** — greenfield. Every app that wants an
   animation currently invents its own number, and one already has.
2. **No haptic vocabulary exists** — the highest-value gap, because
   `HapticFeedback` needs no dependency, so three of four apps can adopt it
   the day this lands.
3. **`tokens.md` is 260 lines against a 250 cap** — it cannot absorb a new
   section, so motion needs a sibling file.

## what

The shared design system has colour, spacing, radius, type and shadow tokens —
and **no motion tokens at all**. Verified 2026-08-16: no `Duration`, `Curve`,
`--duration-*`, `--ease-*`, or haptic constant exists in any stack copy. There is
not even a prose position that motion is out of scope.

Consequence across kuhy's Flutter fleet: **exactly one animation exists in four
apps** — a lone `AnimatedContainer(duration: Duration(milliseconds: 200))` with an
inline magic number. Every other transition is a Flutter/browser default.

Create the motion token layer so the per-app prompts (03–09) have something
canonical to consume instead of each inventing durations.

## where

Repo: `~/utils` (git repo, has CI + the file-length gate wired).

**Create** `~/utils/unified-design-system/motion.md` — the prose freeze.

**Do NOT append to `~/utils/unified-design-system/tokens.md`.** It is 260 lines
and the cap is 250, so it already fails the gate; adding to it makes that worse.
`screen-size.md` was split out of it for exactly this reason — follow that
precedent and add a pointer line in `tokens.md` only if you can do so without
growing it (i.e. by shortening another line).

Then mirror the tokens into the three code stacks:

| Stack | File | Form |
|---|---|---|
| Flutter/Dart | `~/utils/design_system/lib/src/tokens.dart` | `class AppDuration` / `class AppCurve` |
| web/React | `~/utils/web_ui/src/tokens.css` | `--duration-*`, `--ease-*` custom props |
| Python/Tkinter | `~/utils/gatelock/gatelock/_window.py` (`class LockConfig`) | int ms fields — **only if meaningful**; see `must not` |

There are **three** code stacks plus the prose freeze. Do not go hunting for a
fourth — it does not exist.

## must

- Define a **small** scale. Recommended, but use judgement:
  `instant 0ms · fast 120ms · base 200ms · slow 320ms`, and easing
  `standard (0.2, 0, 0, 1)` · `decelerate (0, 0, 0, 1)` · `accelerate (0.3, 0, 1, 1)`.
  Justify each value in `motion.md` in one line — the file is a freeze, so the
  reasoning has to survive without you.
- Include a **haptic** vocabulary mapped to Flutter's `HapticFeedback` API:
  which semantic event gets `selectionClick` vs `lightImpact` vs `mediumImpact`.
  This is the highest-value part — `HapticFeedback` needs no dependency, so
  three of four apps can adopt it immediately.
- Include a **sound** vocabulary: named semantic cues (`confirm`, `complete`,
  `error`) with the rule that sound ships **on** (opt-out) per app, and that
  each app owns its own asset files.
- State the reduced-motion contract in `motion.md`: web uses
  `@media (prefers-reduced-motion: reduce)`, Flutter uses
  `MediaQuery.of(context).disableAnimations`. Motion tokens collapse to `0ms`
  under it; **haptics and sound are unaffected** (they are not motion).
- Keep every file at or under **250 lines** (`~/utils/file_length/config.py`,
  `MAX_LINES = 250`). `.md` and `.py` are capped; `.css` is not.
- **Cut tags at the end** — this is the step that makes the work reach consumers:
  - `design_system-v0.2.0` (consumed by `~/todo`, currently on `v0.1.0`)
  - `web_ui-v0.3.2` (consumed by `~/dufs-cloud/web`, currently on `v0.3.1`)
  Print both tag names at the end of the session; prompts 06, 07 and 08 need them.

- must not: add motion values to the Tkinter `LockConfig` just for symmetry.
  Tkinter has no animation framework. If a duration has no meaning there, mark
  the row `n/a (tk)` in `motion.md` and leave the Python alone. An honest `n/a`
  beats a dead constant.
- must not: express any motion token as a hex-looking value. The existing
  `palette_check.py` parses `#RRGGBB` and would either ignore it or trip on it.
- must not: touch any colour token, or add a colour alongside the motion work.
  That *would* break `palette_check.py`'s completeness half.
- must not: add `# noqa` or `type: ignore` anywhere.

- optional: a `prefers-reduced-motion` helper in
  `~/utils/design_system/lib/src/` and/or `web_ui/src/` so consumers get the
  collapse behaviour without reimplementing it. Nice, not required.

## done

All four hold:

1. `~/utils/unified-design-system/motion.md` exists, is ≤250 lines, and defines
   duration, easing, haptic and sound vocabularies with a one-line rationale each.
2. `python3 ~/utils/file_length/check.py` (or
   `~/utils/scripts/check_file_length.sh --all`) reports **no new** violations.
   `tokens.md` (260), `nielsen-audit.md` (258) and `README.md` (257) are
   pre-existing failures — do not fix them here, but do not add a fourth.
3. `python3 ~/utils/unified-design-system/scripts/palette_check.py` still exits 0.
4. Both tags exist: `git -C ~/utils tag | grep -E 'design_system-v0.2.0|web_ui-v0.3.2'`
   prints two lines.

## verify

Desktop, any way you like — this prompt ships no UI. Run the two gate commands in
`done` and paste their output. Then confirm the token names you chose are what
prompts 03–09 will reference by printing the Dart class and the CSS custom-prop
block.

## read first

- `~/utils/unified-design-system/tokens.md` — the existing freeze; match its
  table format and tone exactly. Note its length problem before editing.
- `~/utils/unified-design-system/screen-size.md` — the precedent for a sibling
  file split out of `tokens.md` (32 lines; short and self-contained).
- `~/utils/design_system/lib/src/tokens.dart` — `AppPalette`, `AppSpacing`,
  `AppRadius`, `AppTextSize`. Your `AppDuration`/`AppCurve` sit alongside these.
- `~/utils/web_ui/src/tokens.css` — the full custom-prop list.
- `~/utils/design_system/lib/src/feedback.dart` — `showToast`/`showError` and
  `_show`. `confirm.dart` next to it **already imports
  `package:flutter/services.dart`**, so `HapticFeedback` is one call away with no
  new import. This is the natural home for a shared haptic helper.
- `~/utils/unified-design-system/scripts/palette_check.py` — read the four
  `parse_*` regexes to see why motion tokens are invisible to it. Prompt 02
  builds the checker that covers them; **do not extend this script here.**

## context you would otherwise rediscover

- **Green CI does not mean no drift for these tokens.** `palette_check.py` only
  matches `#RRGGBB`, so a `--duration-fast: 120ms` is invisible to every one of
  its parsers. `palette_map.py:159` claims structural values are "checked by the
  scale check" — **no such script exists**. Prompt 02 writes it.
- `~/utils/gatelock/` is a package inside the `~/utils` monorepo, not a
  standalone repo. It is consumed as a pinned git dependency.
- Only `~/todo` depends on `design_system`; diet-guard, workout_app and
  wake_alarm hand-transcribe the token values into local `lib/ui/theme.dart`
  copies. So tokens added here reach exactly one app automatically — the others
  are handled per-prompt.

REMOVE ME AFTER FINISH
