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
  split, is never in force on a real day:

  | done | shutdown |
  |---|---|
  | nothing | 19:00 |
  | workout (110) | 20:50 |
  | + LeetCode (50) | 21:40 |
  | + reading (30) | 22:10 |
  | + Anki (25) | 22:35 |
  | + Automation (25) | 23:00 |

  A second workout earns nothing more (`Rung.extra` defaults to 0).
  Move the alarm (`WAKE_MINUTES = 6 * 60`) and the whole ladder shifts an hour
  earlier on its own. Days before `LADDER_FROM` keep their frozen 23:00
  ceiling, so the change never rewrites history.

The two floors are derived separately (`_resolve._shutdown_floor`), so the
ladder cannot move a gaming minute.

**The tutor cutover (`TUTOR_FROM`, one constant in `_ladder.py`).** The
registry is per day: `earners_for(day)` is `EARNERS` before it and
`TUTOR_EARNERS` from it. From `TUTOR_FROM` Anki is retired (neither penalised
nor paid) and `automation` is `AUTOMATION_TUTOR`, a counted earner on the
Automation tutor's ledger (`~/.local/share/automation_tutor/ledger.json`,
`tutor_match` on `detail.ended_at`). Since 0.8.0 it pays per **active
minute** (a unit is one minute), at most 60 a day summed across sessions:

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
- What the writer (plc-lab `plc_lab/tutor/credit.py`) must guarantee: every
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

Days before `TUTOR_FROM` resolve on
`EARNERS` exactly as before. Consumers must iterate `earners_for(day)`, never
`EARNERS`; `resolve`/`base_for` default to it, and ignore answers for an
earner of another day's registry.

**The gap waiver (`ANKI_WAIVED_FROM`, 2026-10-09).** anki-guard never wrote a
credit, and the tutor is not confirmed yet, so from `ANKI_WAIVED_FROM` until
`TUTOR_FROM` the registry is `EARNERS` without `anki` and `automation`:
neither penalised nor paid. The base rises by exactly what the two could have
paid back (nothing done: 4 h / 19:00, pre-ladder; everything done: still
8 h / 23:00), so it can only ever raise time. `TUTOR_FROM` is 2026-10-10
(0.6.1), the day after the deploy, never the deploy day; the waiver therefore
covers 2026-10-09 only. The tutor has no `confirmed_on` yet, so it stays `new`.

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
  over `earners_for(day)` (two earners share the name `automation`), to `resolve`
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

- `resolve(answers, day=None, earners=EARNERS) -> Resolution` — the one sum.
- `base_for(day=None, earners=EARNERS) -> Base` — the day's floors.
- `done_today(earner, ledger, key_file, *, now=None) -> bool | None`
- `first_credit_at(earner, ledger, key_file, day) -> float | None` — unix time
  of the earliest verified credit that counts for `day`. The time is the
  stamp the earner's `match` decides on (`_match.CREDIT_STAMPS`: LeetCode
  `submitted_at`, reading `ended_at`, workout `completed_at`; Anki/Automation
  fall back to `created_at`). It can lie outside `day` when a gate's day is
  not the calendar day (Anki's rollover, a rest day declared the evening
  before).
- `credit_units(earner, ledger, key_file, day) -> int | None` — the units
  the verified rows pay for `day`: 1 per row (the workout), or the row's own
  count (the tutor's `detail.minutes`, legacy block rows 15). A repeated
  `entry_id` pays once, its smallest count; `max_units` is applied by
  `resolve`.
- `earners_for(day)`, `all_earners()`, `registries()` — the registry in force
  on a day, and every earner of every registry (what a ledger watcher must
  watch). They read `earned_time.EARNERS` through the package, so a consumer
  test that patches it still registers its stand-in.
- `shutdown_minutes_for(earner, day) -> int`,
  `extra_shutdown_minutes_for(earner, day) -> int`,
  `shutdown_ceiling_for(day) -> int`, `on_ladder(day) -> bool` — what a status
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
pip install --user --break-system-packages --no-deps "earned-time @ git+https://github.com/kuhyx/utils@earned-time-v0.8.0#subdirectory=earned_time"
```

The root `steam-backlog-enforcer.service` sets `HOME=/home/kuhy`, so it imports
from the same user site-packages.

## Test

```console
scripts/run_subproject_tests.sh earned_time
```
