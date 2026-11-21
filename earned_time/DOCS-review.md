# The LeetCode review top-up (0.23.0)

kuhy's decision, 2026-11-21 (Q12-Q14): a finished coach review
(`/leetcode review`) pays `REVIEW_SHUTDOWN_MINUTES` (20) shutdown minutes, for
the first paid review of the day only, and 0 gaming minutes. `REVIEW` is in the
registry from `REVIEW_FROM` (2026-11-23, the day after the planned deploy);
`confirmed_on` stays unset until kuhy has seen a real review credited.

**A top-up, not a rung.** `Earner.topup` is `True` for it: it is not on the
ladder, it does not lower the floor, and it has no penalty (maturity lists it as
"a top-up: nothing to cut, never penalised"). `resolve` adds its 20 to the
day's shutdown and caps the sum at the ceiling, so a day where everything else
is done gains nothing. On a sick day it is added to the sick shutdown, under
the same cap. Its `kind` stays `"flat"` on purpose: consumers that filter
`kind == "flat"` (screen-locker's live pass and reset stamps) pay it with only
a pin bump. A new `kind` literal would have dropped it from that path.

**The row** (the coach's own ledger, `REVIEW_LEDGER` =
`~/.local/share/leetcode-coach/review_ledger.json`, `{"version": N, "entries": [...]}`),
signed with `entry_signature` and the same shared key as every other ledger:

```json
{"entry_id": "review:<slug>", "kind": "credit", "day": "<YYYY-MM-DD>",
 "created_at": "<iso>", "amount": 1, "device": "pc",
 "detail": {"title_slug": "<slug>", "cause": "<id>",
            "source": "leetcode-coach-review", "finished_at": "<unix seconds>"},
 "hmac": "<entry_signature>"}
```

A row pays (`paid_reviews`, through `done_today`/`credit_units`) only if all hold:

- its signature verifies and `detail.source == REVIEW_SOURCE`;
- `finished_at` falls in the day's window (`day` is the fallback, as for
  `leetcode_match`, but a row without a usable `finished_at` still pays
  nothing, because the lookback needs the time);
- it is the earliest signed review row for its `title_slug`: each slug pays once
  ever, and a later row for the same slug, on any day, pays nothing;
- the guard ledger (`GUARD_LEDGER`, the `LEETCODE` ledger) holds a signed,
  non-manual `credit` row with `detail.source == "leetcode"`, the same
  `title_slug`, and `submitted_at` within `ACCEPTED_LOOKBACK_DAYS` (14) before
  `finished_at`. Manual means a `manual`/`manual_grant` source, a `manual:`/`manual_grant:`
  id, or a `detail.manual_grant` note.

The guard ledger is found under the same home as the review ledger
(`guard_ledger_for`): pass `home / REVIEW.ledger`. Failure paths, all closed:
no review row in the window is `False` (the guard ledger is never read); a
missing or unreadable guard ledger, or a review ledger that is not at
`home / REVIEW.ledger`, is `None` with one warning; a row with no slug or a bad
stamp pays nothing, with a warning. `None` earns nothing, like every "could not
check". The amount is ignored: one row is one unit, and the day pays 20 at most.
