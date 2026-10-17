# earned_time

Penalty-then-reward for gate apps: **one** table of what every gate earns in
gaming time and shutdown time, read by both consumers.

| consumer | applies | via |
|---|---|---|
| steam-backlog-enforcer | `Resolution.gaming_minutes` | `_budget_resolve.resolve_budget` |
| screen-locker | `Resolution.shutdown_minutes` | `_shutdown_base.reset_to_base_if_new_day` + live pass |

A gate (leetcode-guard, book-guard, anki-guard, screen-locker's workout
credit, ...) never touches either. It publishes a fact — HMAC-signed `credit`
rows in its ledger — and is registered here once.

## The model

**Gaming** (unchanged): a base of 5 h, minus every earner's `gaming_minutes`
from its `penalty_from` date; each earner done adds its `gaming_minutes` back.
Capped at 8 h.

**Shutdown** has two regimes, switched by date (`LADDER_FROM`, 2026-10-10 —
never a same-day cut):

- **Before `LADDER_FROM`:** base 20:00 minus the penalties in force, plus
  each earner's `shutdown_minutes` (a second workout +60), capped at 23:00.
- **From `LADDER_FROM` — the sleep ladder.** The ceiling is eight hours of
  sleep before the alarm: `WAKE_MINUTES` (07:00) − 8 h = 23:00. The floor is
  that ceiling minus the sum of every registered earner's rung (a `Rung` per
  earner name; all of a counted earner's capped units), so doing everything
  lands exactly on the ceiling. Since 0.6.1 `TUTOR_FROM == LADDER_FROM`, so
  every real ladder day uses `TUTOR_LADDER` (below); `LADDER`, the pre-tutor
  split (workout 110, LeetCode 50, reading 30, Anki 25, Automation 25; floor
  19:00), is never in force on a real day.

  A second workout earns nothing more (`Rung.extra` defaults to 0).
  Move the alarm (`WAKE_MINUTES = 6 * 60`) and the whole ladder shifts an hour
  earlier on its own. Days before `LADDER_FROM` keep their frozen 23:00
  ceiling, so the change never rewrites history.

The two floors are derived separately (`_resolve._shutdown_floor`), so the
ladder cannot move a gaming minute.

**Unified ladder (0.12.0, `UNIFIED_FROM` 2026-10-18):** each rung pays what
its earner pays in gaming (workout 120, LeetCode 60, reading 60, tutor 1/unit
to 60), so the floor drops 18:50 -> 18:00 under the same 23:00 ceiling:
nothing 3 h / 18:00, workout 5 h / 20:00, +LeetCode 21:00, +reading 22:00.

**Sick days (0.11.0, `_sick.py`).** `resolve(..., sick=True)` floors the
*final* shutdown at 20:00 (`SICK_SHUTDOWN_FLOOR_MINUTES`), capped at the
ceiling: 18:50 becomes 20:00, 21:30 stays 21:30 (nothing stacks on the floor).
Base, terms, gaming, waivers and penalties are unchanged; earners still earn.
`sick` is the consumer's answer (`sickdays.is_sick_day`, never imported here).
Live credits are paid out of `Resolution.sick_lift_minutes` first (a grace lift).

**The tutor cutover (`TUTOR_FROM`, one constant in `_ladder.py`).** The
registry is per day: `earners_for(day)` is `EARNERS` before it and
`TUTOR_EARNERS` from it. From `TUTOR_FROM` Anki is retired (neither penalised
nor paid) and the tutor is `TUTOR` (name `tutor`), a counted earner on the
tutor's ledger (`~/.local/share/tutor/ledger.json`, `tutor_match` on
`detail.ended_at`). Until 0.9.0 it was `AUTOMATION_TUTOR`, name `automation`,
on `~/.local/share/automation_tutor/ledger.json`; rows carry no earner name,
so the rename only moved the ledger (copied whole, old rows still pay).
Since 0.8.0 it pays per **active
minute** (a unit is one minute), at most 60 a day summed across sessions.
**Weekday quota (0.10.0, `TUTOR_QUOTA_FROM` 2026-10-12, `_quota.py`):** all 60
units take 15 min Tue-Thu (`WORKDAYS`, a copy of freedays'), 30 Mon/Fri, 50
Sat/Sun; `credit_units` scales the day's deduped minute sum,
min(60, minutes * 60 // quota), so it returns units, no longer minutes:

| units | gaming | shutdown rung |
|---|---|---|
| each minute | +1 min | +1 min (`Rung(1, extra=1)`) |
| all 60 | +60 (Anki's 30 folded in) | +60 (Anki's 25 folded in) |

Each minute earns exactly the shutdown it costs (the fairness rule). Once its
penalty has started, the gaming base drops by the full 60
(`Earner.max_gaming_minutes`) and the ladder floor by the full 60, so nothing
done is 3 h / 18:50 and everything done is still 8 h / 23:00. Until then
(given `first_credits`, see below) it costs nothing: 4 h / 19:50.

**The tutor row contract (0.8.0, mixed-day safe).** `credit_units` sums what
each counting row pays instead of counting rows (`_credits.row_units`, the
per-matcher reader `_match.ROW_UNITS`):

- `detail.minutes` (a positive JSON int, never a bool/float/string) is the
  active minutes the row pays. A row **without** it is a 0.7.0 15-minute
  block and pays 15 (`LEGACY_TUTOR_MINUTES`), so a day that mixes block rows
  and minute rows sums both, and an all-block day resolves exactly as 0.7.0
  did (min(15 n, 60) = 15 min(n, 4)). A row whose `minutes` is present but
  invalid is refused by `tutor_match` (logged) and pays nothing anywhere.
- An `entry_id` pays once; rows repeated under one id pay the **smallest**
  of their counts, so a replay or a rewrite can never raise a credit.
- What the writer ([kuhyx/tutor](https://github.com/kuhyx/tutor) `tutor/credit.py`) must guarantee: every
  new row carries `detail.minutes`; one row per credited minute,
  `entry_id = f"{session_id}-m{n}"` with `n` the session's n-th credited
  active minute (deterministic, so a retry rewrites the same id; never the
  `-b{n}` form); ids never cover overlapping minutes (no cumulative "total so
  far" rows); `detail.ended_at` is when the last paid minute ended (it picks
  the day, so a multi-minute row must never span local midnight); its own
  daily cap sums minutes (block rows as 15) up to 60. N-minute rows (e.g.
  every 5 minutes) are allowed under the same rules; each write fires
  screen-locker's `earner-bonus.path`, so per-minute rows rewrite the
  shutdown schedule once a minute.
- Rollout order: no minute row may be written until every consumer process
  runs 0.8.0. A 0.7.0 reader pays each row as a 15-minute block.

Days before `TUTOR_FROM` resolve on `EARNERS` exactly as before. Consumers must
iterate `earners_for(day)`, never `EARNERS`; `resolve`/`base_for` default to
it, and ignore answers for an earner of another day's registry.

**The gap waiver (`ANKI_WAIVED_FROM`, 2026-10-09).** anki-guard never wrote a
credit, and the tutor is not confirmed yet, so from `ANKI_WAIVED_FROM` until
`TUTOR_FROM` the registry is `EARNERS` without `anki` and `automation`:
neither penalised nor paid. The base rises by exactly what the two could have
paid back (nothing done: 4 h / 19:00, pre-ladder; everything done: still
8 h / 23:00), so it can only ever raise time. `TUTOR_FROM` is 2026-10-10
(0.6.1), the day after the deploy, never the deploy day; the waiver therefore
covers 2026-10-09 only. The tutor was confirmed in 0.7.0 (`confirmed_on`
2026-10-09), so its penalty bites from `TUTOR_FROM`.

## Gate maturity (0.6.0)

How far to trust a gate is computed from its ledger, never listed by name:
`maturity(earner, ledger, key_file, today) -> Maturity` (`_maturity.py`).

- **Real credit:** HMAC-verified `credit` row, accepted by the earner's
  `match`, not manual (`detail.source` `manual`/`manual_grant`, `entry_id`
  `manual:`/`manual_grant:`), and `amount > 0` when the row has one -- a
  gate's own re-evaluation grant (`detail.grant_of`, book-guard `bonus:`
  rows) may pay 0. A matcher cannot loosen this (`anki_match` alone accepts a
  `manual_grant` row).
- **Levels:** `new` = no real credit, or no `Earner.confirmed_on` (set by
  kuhy); `mature` = at least `MATURE_MIN_CREDIT_DAYS` (14) distinct credit
  days and the first at least `MATURE_MIN_AGE_DAYS` (21) old; else `maturing`.
  An unreadable ledger or key is `checked=False`, `new`, reason recorded.
- **Penalty start:** `penalty_start(earner, first_credit)` =
  max(`penalty_from`, day after the first real credit, day after
  `confirmed_on`). No first credit (never paid out, or could not check) is
  not penalised -- unless `confirmed_on` is set: then fail closed,
  max(`penalty_from`, day after `confirmed_on`), so deleting or locking a
  ledger cannot lift a penalty. Pass `first_credits={name: Maturity.first_credit}`, computed
  over `earners_for(day)` (until 0.9.0 two earners shared the name `automation`), to `resolve`
  / `base_for` to apply it; omitted, a penalty starts at `penalty_from`, as
  in 0.5.0. It can only delay a penalty, never add one.
- **Ladder floor (0.6.1):** the same start gates the shutdown floor. A rung
  comes off the floor only for a pure bonus (no `penalty_from`: workout,
  LeetCode) or an earner whose penalty has started, so a gate that never paid
  out cannot lower it either (10-10, tutor never credited: 19:50, not 19:00).
  An unwired consumer (no `first_credits`) cuts the tutor from `penalty_from`:
  19:00 / 3 h.
- **CLI:** `python -m earned_time maturity [--json] [--day YYYY-MM-DD]`
  prints one row per ledger-backed earner of every registry. It is the only
  code that resolves real paths (`~/<Earner.ledger>`,
  `/etc/workout-locker/hmac.key`), and it only reads.

## API

- `resolve(answers, day=None, earners=None, *, first_credits=None, sick=False)`
  `-> Resolution` — the one sum. `sick_shutdown_minutes(minutes, day) -> int`.
- `base_for(day=None, earners=EARNERS) -> Base` — the day's floors.
- `done_today(earner, ledger, key_file, *, now=None) -> bool | None`
- `first_credit_at(earner, ledger, key_file, day) -> float | None` — unix time
  of the earliest verified credit for `day`, on its matcher's stamp
  (`_match.CREDIT_STAMPS`; Anki/Automation: `created_at`). It can lie outside
  `day` (Anki's rollover, a rest day declared the evening before).
- `credit_units(earner, ledger, key_file, day) -> int | None` — the units
  the verified rows pay for `day`: 1 per row (the workout), or the row's own
  count (the tutor's `detail.minutes`, legacy block rows 15; from 0.10.0 the
  day's sum scaled to its weekday quota). A repeated `entry_id` pays once,
  its smallest count; `max_units` is applied by `resolve`.
- `earners_for(day)`, `all_earners()`, `registries()` — the registry in force
  on a day, and every earner of every registry (what a ledger watcher must
  watch). They read `earned_time.EARNERS` through the package, so a consumer
  test that patches it still registers its stand-in.
- `shutdown_minutes_for(earner, day) -> int`, `extra_shutdown_minutes_for(earner,
  day) -> int`, `shutdown_ceiling_for(day) -> int`, `on_ladder(day) -> bool` — what a status
  view needs to list what is still left to earn. `Earner.shutdown_for(units,
  day=None)` is the day-aware sum (default today). Never read
  `earner.shutdown_minutes` directly: it is the pre-ladder value.
- `day_window(day)`, `today_window(now=None)`, `entry_signature`, `verified`.

## The workout ledger

`WORKOUT` is `kind="counted"` with a ledger at
`~/.local/share/workout_locker/ledger.json`, written by screen-locker: one
signed credit row per credited unit,
`{"kind": "credit", "entry_id", "day", "detail": {"completed_at", "source"}}`.
`workout_match` counts a `runnerup_tcx` row when `completed_at` falls in the
window, and a `rest_day` row on the `day` it names — only if
`detail.declared_at` is before that day's local midnight. A rest day declared
on the day itself is logged and does not count.

## Adding a gate

1. The gate writes `{"entries": [...]}` to its ledger. Each row has
   `kind: "credit"`, a `detail` dict, and an `hmac` signed with
   `/etc/workout-locker/hmac.key` (`earned_time.entry_signature`, the same as
   gatelock's `log_integrity`).
2. Add a matcher to `earned_time/_match.py` and an `Earner` to
   `earned_time/_policy.py` and `EARNERS`:

   ```python
   PIANO = Earner(
       name="piano",                    # also screen-locker's "piano_bonus_date" stamp
       label="piano",
       gaming_minutes=30,
       shutdown_minutes=30,             # pre-ladder value
       penalty_from=date(2026, 11, 1),  # gaming base drops by 30 from then on
       ledger=".local/share/piano_guard/ledger.json",
       match=piano_match,               # which verified credit rows count today
       missing_ledger_is_no=True,
   )
   ```

   Then give it a rung in `TUTOR_LADDER` (`PIANO.name: Rung(20)`), and, if its
   matcher decides on an event stamp, an entry in `_match.CREDIT_STAMPS`.

   On the ladder a new earner's rung comes out of the floor from its
   penalty start (a pure bonus: the day its pin lands; the ceiling is fixed):
   re-split the rungs and ship it the day the
   gate can actually be satisfied.
3. Bump the version, tag `earned-time-vX.Y.Z`, and bump the pin in both
   consumers. Neither needs code for a ledger-backed flat earner.

## Rules the consumers rely on

- **Minutes everywhere.** Shutdown is minutes after local midnight.
- **Paths are passed in.** No reader resolves a real path itself; consumers'
  test suites redirect their own constants.
- **`None` is "could not check", never "no".** It earns nothing (fail closed),
  but consumers log it. A missing answer in `resolve()` is logged as well; an
  unknown earner name raises.
- **The HMAC key is root-owned and 0644 on purpose.** The gates run as the
  user and must sign their rows, so the user can read the key; root owns it
  so a user process cannot replace or rotate it. The signature therefore
  stops casual edits and corruption, not a determined forger with a shell --
  the accepted trade-off of user-run gates.
- **Stdlib only.** The gaming daemon imports this as root, headless.

## Install

```console
pip install --user --break-system-packages --no-deps "earned-time @ git+https://github.com/kuhyx/utils@earned-time-v0.12.0#subdirectory=earned_time"
```

The root `steam-backlog-enforcer.service` sets `HOME=/home/kuhy`, so it imports
from the same user site-packages. Test: `scripts/run_subproject_tests.sh earned_time`.
