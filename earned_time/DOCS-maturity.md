# earned_time: gate maturity (0.6.0)

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
  prints one row per ledger-backed earner of every registry. It and
  `leisure_from()` alone resolve real paths (`~/<Earner.ledger>`,
  `/etc/workout-locker/hmac.key`), and it only reads.
