Surface the workout streak that screen-locker already tracks

## findings (3, ranked by value over effort)

1. **`snapshot.streak` is populated and no renderer reads it** — the cheapest
   win in the whole project. Zero new state, zero conftest change, zero deps.
2. **Week-transition reward strings are discarded into `_logger.info`** —
   fully-formed celebratory sentences that never reach a user.
3. **The success moment exists only on the lock screen**, for 1.5s. The status
   window — the surface visited *voluntarily* — shows only enforcement.

## what

screen-locker computes a real workout streak and celebratory reward text, then
throws almost all of it away. Verified 2026-08-16:

- `StatusSnapshot` (`screen_locker/_status_types.py` ~:88-101) carries populated
  `streak`, `bonus_hours_this_week` and `early_bird_extended` fields, filled by
  `_status_data.py` ~:210-214. **Grep confirms no renderer reads them.**
- `_extra_benefits.py` `process_week_transition()` (~:82, reward strings built at
  ~:130-139) produces fully-formed celebratory sentences — and
  `_startup_checks.py` ~:57-58 sends them to `_logger.info` and nowhere else.
- The one success moment that exists is on the **lock screen**:
  `_unlock_view.py` `unlock_screen()` (~:25) paints "Great job! 💪" and
  `🔥 {streak}-week streak`, for `_UNLOCK_DELAY_MS = 1500` before routing away.

So the surface the user visits **voluntarily** — the status window, opened from
the tray icon — shows enforcement and budget depletion, and no evidence of
success at all. This is the cheapest high-value change in the whole project:
the data already exists, is already true, and needs no new state.

## where

Repo: `~/screen-locker`.

Primary:
- `screen_locker/_status_sections.py` — the section renderers used by the status
  window (`_section_*` functions). **177 lines; has headroom.** Add
  `_section_streak` here.
- `screen_locker/status_view.py` — `StatusWindow`, `render()`. Call the new
  section from here. ⚠️ **246 lines — only 4 left under the 250 cap.** Expect to
  extract something, or add the call in a way that costs ~1 line.
- `screen_locker/_status_types.py` — `StatusSnapshot` (~:88-101), the fields you
  are rendering. Read-only for this task.
- `screen_locker/_extra_benefits.py` (179 lines) — `process_week_transition()`
  and its reward strings; `current_streak()` ~:154,
  `weekly_shutdown_bonus_hours()` ~:159, `has_extended_early_bird()` ~:171.
- `screen_locker/_startup_checks.py` ~:57-58 — where the reward strings are
  currently discarded into a log call.
- `screen_locker/_unlock_view.py` (72 lines, lots of headroom) — the existing
  success moment, if you extend it.

## must

- **Render the already-populated fields.** Add `_section_streak` to
  `_status_sections.py` showing the weekly streak, this week's bonus hours, and
  the extended-early-bird state, and call it from `status_view.py`'s `render()`.
  Zero new state, zero conftest change, zero new dependency.
- **Stop discarding the reward strings.** `process_week_transition()` returns
  human-readable celebratory sentences that currently only reach the log. Surface
  them where the user will actually see them — the status window is the obvious
  home; a milestone is worth more than a silent counter increment.
- Match the existing positive-status styling rather than inventing one:
  `_status_sections.py` ~:73-78 already renders `"{n} above the weekly minimum!"`
  in success green, and uses `✓` marks at ~:36 and ~:57.
- Keep the streak **true**. It counts real ISO weeks with ≥5 counted workouts
  (`_weekly_check.py`: `WEEKLY_WORKOUT_MINIMUM = 5`, `COUNTED_WORKOUT_TYPES =
  {phone_verified, runnerup_verified, manual_workout}`). Do not round, pad, or
  "encourage" the number.

- must not: **make any reward reduce enforcement.** This is recorded twice in the
  repo as a deliberate decision:
  > `_startup_checks.py` ~:88-93 — "there is no banked 'skip a workout' credit —
  > that mechanic works against the goal of maximizing weekly workouts, so it was
  > removed in favor of a shutdown-time-only reward"
  > `_extra_benefits.py` ~:5-8 — "This never reduces enforcement … it only grants
  > extra comfort time on top of a floor you still have to earn each day."

  Every reward here is **display or comfort-time only**. Do not reintroduce a
  banked skip, a streak freeze, a grace day, or any mechanic that lowers the
  floor. A dopamine loop that lets you skip the workout defeats the app.
- must not: add **sound** to any enforcement or lock path. screen-locker is a
  self-restriction tool; a chime on lock is punishment audio, and a chime on
  unlock trains the wrong association. This repo stays silent. (Sound is
  opt-out-on elsewhere in the fleet; here it is simply absent.)
- must not: add a write tool to the MCP server. `_mcp.py` ~:14-26 states it is
  read-only by design. Adding `streak` to the existing `get_status` output is
  fine; a new action tool violates a stated invariant.
- must not: add `# noqa` (banned repo-wide) or a silent `except`
  (`scripts/check_silent_failures.py` — every handler re-raises or logs at
  warning or above).
- must not: create a new on-disk state file unless genuinely unavoidable. If you
  do, you **must** add it to `_ISOLATED_STATE` in
  `screen_locker/tests/conftest.py` (~:134), listing *every* module that binds
  the path at import time — a missed binding lets tests write to kuhy's real
  state. Read the comment at ~:131-133 and the fixture docstring at ~:170-175.

- optional: a daily streak alongside the weekly one. Note this **would** be new
  state (the existing streak is consecutive-*weeks*), so it triggers the conftest
  requirement above. diet-guard's consecutive-*day* streak
  (`~/diet-guard/diet_guard/_daystatus.py` ~:144) is the precedent to mirror.

## done

1. Opening the status window (tray icon → click, or `screen-locker-status`) shows
   the current streak, bonus hours and early-bird state — with the real values
   from `extra_benefits_state.json`, not placeholders.
2. A week-transition milestone reaches the UI instead of only `_logger.info`.
3. `cd ~/screen-locker && python -m pytest` passes.
4. `pre-commit run --files <changed files>` is clean — including the 250-line cap
   (`scripts/check_file_length.py`) and the silent-failure check.
5. `git diff` touches no enforcement logic: no change to lock decisions, weekly
   minimums, or shutdown floors.

## verify

Desktop — this is a desktop Python app.

```
cd ~/screen-locker
python -m screen_locker --status          # CLI: confirm the values it prints
screen-locker-status                      # the Tk window: confirm they render
```

Paste both outputs. The CLI already prints `streak`/`bonus_hours` (`_status.py`
~:138-141), so it is your ground truth: the window must show the **same numbers**.
If they disagree, the renderer is wrong, not the data.

Current real state for comparison: `screen_locker/extra_benefits_state.json` and
`screen_locker/workout_log.json` (12 days of entries, 2026-07-12 → 2026-08-15).

## read first

- `screen_locker/_status_sections.py` — every existing `_section_*`. Match their
  signature and style; note the success-green precedent at ~:73-78.
- `screen_locker/_status_types.py` ~:88-101 — the three fields you are rendering.
- `screen_locker/_extra_benefits.py` — especially the module docstring ~:5-8
  (the enforcement invariant) and the reward strings ~:130-139.
- `screen_locker/_unlock_view.py` — the existing celebration, for tone.
- `screen_locker/status_view.py` — check its line count **before** editing.
- `~/screen-locker/CLAUDE.md` — repo rules (no silent failures, ruff `select=ALL`).

## context you would otherwise rediscover

- **`workout_log.json` is the single source of truth**, written only through
  `_log_mixin.py` `write_signed_entry()` (~:82), HMAC-signed via
  `gatelock.log_integrity`, deduped on `workout_id`. The Flutter app converges on
  it via `_manual_push.py`. There is no second history — a streak computed from
  it is authoritative.
- All persistence is **JSON files, no sqlite**; paths declared in
  `screen_locker/_constants.py`. The streak store is
  `screen_locker/extra_benefits_state.json` (`consecutive_5plus_weeks`,
  `last_processed_iso_week`, `weekly_shutdown_bonus_hours`,
  `extended_early_bird_iso_weeks`).
- Thresholds live in `_extra_benefits.py`: `_MILESTONE_INTERVAL = 4` (4-week
  milestone), `_BONUS_THRESHOLD = 5` (workouts per week).
- **There is no config system** — no argparse, no env vars, no config file. Every
  tunable is a module-level constant. An opt-out toggle has no existing home;
  for a self-restriction tool, requiring a code edit to disable is arguably
  correct, so prefer a constant in `_constants.py` over new state.
- `~/gatelock` is **not** a repo — it is `~/utils/gatelock/gatelock/`, consumed as
  a pinned git dep, and it holds no workout state.
- Manual workouts were **not** removed: `_manual_workout.py` implements a
  rate-limited, evidence-gated subsystem (budget 2 per 7 days, 10 per 30).
- Three UI surfaces exist: the Tk status window (`status_view.py`), a GTK tray
  icon at `~/.config/i3/scripts/screen_locker_tray.py` (outside the repo, shells
  out to the CLI, refreshes every 60s), and the lock screen itself. No i3blocks
  integration exists despite `format_summary_line` being described as one.
