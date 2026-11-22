# The tutor row contract (0.8.0)

Moved out of the README (0.24.0) to keep it under the line cap; unchanged.

**Mixed-day safe.** `credit_units` sums what
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

Days before `TUTOR_FROM` resolve on `EARNERS` exactly as before. Consumers must
iterate `earners_for(day)`, never `EARNERS`; `resolve`/`base_for` default to
it, and ignore answers for an earner of another day's registry.
