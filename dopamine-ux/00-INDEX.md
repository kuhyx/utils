# Dopamine UX — session prompts

Ten pasteable prompts derived from *"The Dopamine Architecture: How UX Designers
Hold User Attention in 2026"* (london-post.co.uk), applied to kuhy's repos.

Paste **one file's contents** into a fresh Claude session. Each is
self-contained: it restates the findings it depends on, so no session needs the
context of another.

## The two tests — every change must pass both

The article's four mechanics (variable rewards, micro-animations, sound design,
near-miss) are in scope, aimed at **kuhy's own stated goals**. They are gated by
two questions, not by an allow/deny list:

1. **Is the displayed state true?** A progress ring at 93% is legitimate *iff*
   you are actually at 93%. A streak is legitimate iff it counts real days.
   Dopamine may come from framing, timing and salience — **never from a
   fabricated number**.
2. **Is the variance real?** A random pick from a real pool (next workout, next
   task) is legitimate. Injected random bonus points to manufacture uncertainty
   are not.

### The load-bearing corollary

**Reward the recording, never the number recorded.** In diet-guard the
satisfying moment fires on *logging a meal*, not on hitting a calorie target —
otherwise the app rewards eating less rather than recording honestly, and
corrupts its own data. Same shape in workout_app (reward logging a workout, not
beating a PB) and todo (reward capture, not completion count).

## Running order

`01` gates everything. `07` gates `08`. Everything else is independent.

| # | File | Repo | Findings |
|---|---|---|---|
| 01 | `01-motion-tokens.md` | `~/utils` | 3 |
| 02 | `02-structural-check.md` | `~/utils` | 2 |
| 03 | `03-diet-guard.md` | `~/diet-guard` | 4 |
| 04 | `04-screen-locker.md` | `~/screen-locker` | 3 |
| 05 | `05-workout-app.md` | `~/screen-locker/stronglift_replacement/workout_app` | 4 |
| 06 | `06-todo.md` | `~/todo` | 3 |
| 07 | `07-dufs-theme.md` | `~/dufs-cloud` | 2 |
| 08 | `08-dufs-motion.md` | `~/dufs-cloud` | 4 |
| 09 | `09-wake-alarm.md` | `~/wake-alarm` | 2 |

**27 ranked findings total.**

### Dependency graph

```
01-motion-tokens ──┬─→ 03, 04, 05, 09   (transcribe tokens locally)
                   ├─→ 06               (bump design_system-v0.2.0)
                   └─→ 07 ─→ 08         (bump web_ui-v0.3.2)
02-structural-check  (independent; run after 01 so it has motion tokens to check)
```

## The top three findings fleet-wide

Ranked by value-over-effort from the survey data:

1. **screen-locker streak render** (prompt 04) — `snapshot.streak` is already
   populated and no renderer reads it. Zero new state, zero conftest change,
   zero new dependency.
2. **diet-guard `_onLogMeal` feedback** (prompt 03) — the flagship case.
   Dependency-free via `HapticFeedback` from `flutter/services.dart`.
3. **workout_app finish-workout cue** (prompt 05) — `audioplayers`, `vibration`,
   the `assets:` block and the VIBRATE permission are **already present**. Only
   the call is missing.

## Distributed copies, and the completion protocol

Each prompt is **also copied into the repo it acts on**, at
`<repo>/prompts/dopamine-ux-*.md`, so you can open a repo and say
"do dopamine-ux-<name>" without going hunting. **This directory stays the source
of truth** — if a prompt needs correcting, fix it here and re-distribute.

| Prompt | Distributed to |
|---|---|
| 01 | `~/utils/prompts/dopamine-ux-01-motion-tokens.md` |
| 02 | `~/utils/prompts/dopamine-ux-02-structural-check.md` |
| 03 | `~/diet-guard/prompts/dopamine-ux-diet-guard.md` |
| 04 | `~/screen-locker/prompts/dopamine-ux-04-screen-locker.md` |
| 05 | `~/screen-locker/prompts/dopamine-ux-05-workout-app.md` |
| 06 | `~/todo/prompts/dopamine-ux-todo.md` |
| 07 | `~/dufs-cloud/prompts/dopamine-ux-07-theme.md` |
| 08 | `~/dufs-cloud/prompts/dopamine-ux-08-motion.md` |
| 09 | `~/wake-alarm/prompts/dopamine-ux-wake-alarm.md` |

When a session finishes a prompt it **deletes its repo copy** (in the same
commit as the implementation) and **appends a row below**. A finished prompt left
in a repo is indistinguishable from a pending one, and the next session re-runs
it. Partial completion is never recorded as DONE — the file is edited to state
what remains instead.

### Completion log

| Prompt | Status | Impl commit | Note |
|---|---|---|---|
| 01-motion-tokens.md | DONE 2026-08-22 | `f741896` | `motion.md` frozen; `AppDuration`/`AppCurve` + `--duration-*`/`--ease-*` shipped. Tags: `design_system-v0.2.0`, `web_ui-v0.3.2`. |
| 02-structural-check.md | not started | — | — |
| 03-diet-guard.md | not started | — | — |
| 04-screen-locker.md | not started | — | — |
| 05-workout-app.md | not started | — | — |
| 06-todo.md | not started | — | — |
| 07-dufs-theme.md | not started | — | — |
| 08-dufs-motion.md | not started | — | — |
| 09-wake-alarm.md | not started | — | — |

## Keeping these prompts honest

Every path and symbol cited across these files is machine-checked:

```
python3 ~/utils/dopamine-ux/verify_prompts.py
```

Exit 0 means every cited path resolves and every cited symbol is still greppable
in the file it is attributed to. **Re-run it after any refactor of the surveyed
repos** — a prompt pointing at a renamed function is worse than no prompt, and a
path check alone cannot catch that (which is why it greps symbols too).

Verified 2026-08-16: 146 paths, 30 symbols, all passing.

## Rules that apply to every prompt

1. **Tag cuts and version bumps are explicit steps.** `todo` consumes
   `design_system` at git ref `design_system-v0.1.0`; `dufs-cloud/web` consumes
   `@kuhyx/web-ui` at `web_ui-v0.3.1`. Adding tokens to those packages does
   nothing for consumers until a new tag is cut. Prompt 01 ends by cutting
   `design_system-v0.2.0` and `web_ui-v0.3.2`; prompts 06 and 08 begin by
   bumping to those literal refs.
2. **Anchor on symbols, not line numbers.** Line numbers in these prompts are
   "as of 2026-08-16" and will drift. The symbol name is the real anchor —
   grep for it rather than trusting the line.
3. **Reduce-motion is mandatory and is NOT the sound toggle.** Web:
   `@media (prefers-reduced-motion: reduce)`. Flutter:
   `MediaQuery.of(context).disableAnimations`. The OS motion preference is
   honoured automatically; the sound opt-out is a separate user-facing toggle.
4. **Motion and haptics first, sound second.** Haptics need no dependency;
   sound needs a pubspec dep, an `assets:` block, and a settings toggle. Each
   prompt stages them separately so a short session still lands the valuable
   half, and sound stays independently revertable.
5. **Sound ships on (opt-out), never in screen-locker enforcement paths.**
6. **250-line cap** applies to code and prose alike (`~/utils/file_length`).

## Source

Article findings, verbatim from the piece:

- **Variable reward schedules** — unpredictable outcomes produce stronger
  dopaminergic activity than guaranteed ones. Duolingo streaks, feed ordering,
  pull-to-refresh.
- **Micro-animations** — "a button that bounces on press, a like counter that
  ticks upward with a slight delay". Replaces latency with feedback, so waiting
  reads as responsiveness rather than frustration.
- **Sound design** — "operates below the threshold of conscious attention";
  the article's judgement is that it is more powerful than visual design and
  gets less critical attention.
- **Near-miss effects** — a fitness ring at ninety-three per cent creates
  discomfort that drives re-engagement, and works *even when the user is
  explicitly told the mechanism*.
- Core claim: **dopamine is released in anticipation of a reward, not on
  receipt. The uncertainty is the trigger.**
