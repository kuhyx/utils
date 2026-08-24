# Motion, haptics and sound (frozen values)

Split out of `tokens.md` on 2026-08-22 to hold every file under the shared
250-line cap, when the motion scale was added. Both are part of the same token
spec — this is a filing change, not a scoping change.

> **Not yet checked by a script.** `scripts/palette_check.py` parses `#RRGGBB`
> only, so every value below is invisible to it — a `--duration-fast: 120ms`
> matches none of its four parsers. `palette_map.py:159` claims structural
> values are "checked by the scale check"; no such script exists yet. Until
> dopamine-ux prompt 02 writes it, these three stacks are kept in agreement by
> hand, and editing a value here means editing it in `web_ui/src/tokens.css`
> and `design_system/lib/src/tokens.dart` in the same commit.

## Duration

Four steps. The scale is deliberately short: a duration vocabulary with ten
entries gets picked from at random, which is drift wearing a token's name.

| Token     | Value   | Rationale                                                        |
| --------- | ------- | ---------------------------------------------------------------- |
| `instant` | `0ms`   | No animation. The reduced-motion collapse target, and the honest choice for anything that must feel direct. |
| `fast`    | `120ms` | State on an element already under the cursor/finger — hover, press, checkbox, ripple. Below ~100ms reads as instant, so this is the floor at which motion is perceived *as* motion. |
| `base`    | `200ms` | The default. Anything that enters, leaves or moves within the current view: toasts, expanding rows, tab switches. |
| `slow`    | `320ms` | Full-surface change — sheets, dialogs, page transitions. Above ~350ms the interface feels like it is waiting on itself, so this is the ceiling, not a midpoint. |

Anything needing a duration not on this scale is a signal the interaction is
wrong, not that the scale is short.

## Easing

Three curves, as cubic-bezier control points. Named for what the motion does at
its *end*, because that is the part the eye actually reads.

| Token        | Cubic-bezier         | Rationale                                                    |
| ------------ | -------------------- | ------------------------------------------------------------ |
| `standard`   | `(0.2, 0, 0, 1)`     | The default for anything that starts and ends on screen. Fast out of the gate, settles gently. |
| `decelerate` | `(0, 0, 0, 1)`       | Entering the screen. Starts at full speed (the element is already "in motion" from off-stage) and eases to rest. |
| `accelerate` | `(0.3, 0, 1, 1)`     | Leaving the screen. Eases in, exits at speed — no settle, because there is nothing to settle onto. |

Never `ease-in-out` on an element that enters or exits: symmetric easing makes
an arrival look like it is braking into place and a departure look reluctant.

## Reduced motion — mandatory

Motion tokens collapse to `0ms`. Easing becomes irrelevant at zero duration and
needs no separate handling.

| Stack        | How it is detected                                    |
| ------------ | ----------------------------------------------------- |
| web/React    | `@media (prefers-reduced-motion: reduce)`              |
| Flutter/Dart | `MediaQuery.of(context).disableAnimations`             |
| Python/Tk    | `n/a (tk)` — see below                                 |

**Haptics and sound are unaffected.** They are not motion, and a user who
suppresses animation has not asked to be denied confirmation that a tap landed.
This is the rule most often got wrong by collapsing all feedback under one flag.

The OS motion preference is honoured automatically and is **not** the sound
toggle. The sound opt-out is a separate, user-facing setting (below).

## Haptics

Mapped onto Flutter's `HapticFeedback` API. This is the highest-value row in
this file: `HapticFeedback` comes from `flutter/services.dart` and needs no new
dependency, so an app can adopt it the day it reads this.

| Semantic event                       | Call             | Rationale                                          |
| ------------------------------------ | ---------------- | -------------------------------------------------- |
| Selection changed (tab, chip, picker) | `selectionClick` | The lightest cue available. Fires often, so it must be nearly free. |
| Recorded something (meal, workout, task) | `lightImpact` | The confirming tap. **Fires on the recording, not on the number recorded** — see the corollary below. |
| Completed a whole flow (finished a workout, closed a streak) | `mediumImpact` | Reserved for genuine completion. If everything is `mediumImpact`, nothing is. |
| Error / rejected input               | `heavyImpact`    | Distinct by weight, not just by pattern — the one cue that must be felt without looking. |

**Reward the recording, never the number recorded.** The haptic on *logging a
meal* is legitimate; a haptic on *hitting a calorie target* rewards eating less
rather than recording honestly, and corrupts the app's own data. Same shape in
`workout_app` (reward logging a workout, not beating a PB) and `todo` (reward
capture, not completion count).

## Sound

Three named semantic cues. Each app **owns its own asset files** — this file
freezes the vocabulary and the policy, not the audio.

| Cue        | Fires when                                              |
| ---------- | ------------------------------------------------------- |
| `confirm`  | An action was recorded. Pairs with `lightImpact`.        |
| `complete` | A flow finished. Pairs with `mediumImpact`.              |
| `error`    | Input was rejected. Pairs with `heavyImpact`.            |

Policy:

1. **Sound ships on, as an opt-out.** A cue nobody ever hears is not a cue. The
   toggle is per-app and user-facing.
2. **The sound toggle is not the reduced-motion preference**, and neither
   implies the other. Two settings, two meanings.
3. **Never a cue without its haptic sibling.** Sound is the part that fails —
   silenced phone, no speaker, noisy room — so it is the redundant channel, and
   the haptic carries the meaning alone whenever it has to.
4. Keep cues under ~300ms. A sound outlasting `slow` is still playing after the
   thing it describes has finished.

## Stack mapping

| Stack        | File                                    | Form                                    |
| ------------ | --------------------------------------- | --------------------------------------- |
| Flutter/Dart | `design_system/lib/src/tokens.dart`     | `class AppDuration` / `class AppCurve`  |
| web/React    | `web_ui/src/tokens.css`                 | `--duration-*` / `--ease-*` custom props |
| Python/Tk    | `gatelock/gatelock/_window.py`          | `n/a (tk)`                              |

`n/a (tk)`: Tkinter has no animation framework, and gatelock's `LockConfig`
carries no motion values. Adding them for symmetry would ship a dead constant
that reads as a supported feature — an honest `n/a` beats a lie about scope.
Haptics and sound are likewise `n/a` there: it is a fullscreen desktop lock
surface with no haptic hardware.

Only `~/todo` consumes `design_system` as a package; `diet-guard`, `workout_app`
and `wake_alarm` hand-transcribe these values into local `lib/ui/theme.dart`
copies. Tokens added here therefore reach exactly one app automatically — the
rest is per-app work, which is what dopamine-ux prompts 03–09 are for.
