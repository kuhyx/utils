# Progress: partial pay (0.24.0)

kuhy's rule (2026-11-22): a gate pays its bonus in proportion to progress, in
equal slices, nothing held back. Half the pages is half the bonus. It covers the
shutdown bonus, its gaming twin and sick days.

earned_time cannot derive a gate's plan, so the gate signs a fact, "done N of
target M for day D", and earned_time only reads it. A day with no such row
resolves exactly as 0.23.0 did, for every registry and day.

## The row

One signed ledger row, in the gate's own ledger (`Earner.ledger`):

```json
{"kind": "progress", "entry_id": "progress:<for_day>:<done>:<target>",
 "day": "<for_day>", "amount": 0, "device": "...", "created_at": "...",
 "detail": {"source": "<progress source>", "for_day": "YYYY-MM-DD",
            "done": "<digits>", "target": "<digits>"},
 "hmac": "<entry_signature>"}
```

All four `detail` values are strings. The sources: `workout`, `leetcode`,
`reading`, `review` (`Earner.progress_source`; the tutor and the focus earner
have none and never pay by share).

## The reader

`read_progress(earner, ledger, key_file, day, *, gate_off=False)` returns a
`Progress(done, target)` or `None`. A row counts only when all of this holds:

- its HMAC verifies with the shared key;
- `kind` is `progress`;
- `detail.source` is the earner's `progress_source`;
- `detail.for_day` is the day asked;
- `done` and `target` are strings of ASCII digits 0-9, at most nine of them
  (no int, float, sign, space, empty string or other script's digits);
- `target` is at least 1.

`done` is capped at `target`. Over the matching rows the largest `done` and the
largest `target` win, so a replayed or deleted row can only lower the share
while the target stays the same.

`progress_map(day, home, key_file, *, earners=None, gate_off=())` does this for
every earner of `earners_for(day)` (or the registry given) and returns
`{earner name: Progress}`, holding only earners that have a fact. Pass the names
of the earners whose gate is off today as `gate_off`, as for `done_today`.

## The pay

`resolve(answers, day, ..., progress=progress_map(...))`. A term uses its
progress only when its answer is `0` or `False`, and then pays
`full * done // target`, floored, where `full` is what a yes pays that day: the
ladder rung for shutdown (`shutdown_minutes_for`), the earner's first-unit pay
for gaming. A true answer pays full exactly as before, whatever the row says.
An answer of `None` ("could not check") and a missing answer still earn nothing,
even beside a complete row. `Term.progress` holds the fact a term was paid from
(`None` otherwise), so a view can show why. A sick day adds each term's pay
to 20:00, so a partial pays its share at rung pay, capped at the ceiling.

The focus earner already paid N/M floored; it now calls the same arithmetic
(`_share.share_minutes`), with the same floor.

## Every failure is fail-closed

`None` means "pays by today's yes/no rule", never more. Each of these is `None`:

- no row for the earner and day: the gate has said nothing;
- a bad or missing signature, or a row edited after signing: a forged claim;
- another day or another gate's source: a fact about something else;
- bad integers (typed as numbers, signed, padded, empty, too long): unreadable;
- a zero target: no plan, so no share;
- an unreadable or empty key, an unreadable or malformed ledger: logged at
  warning, never raised;
- `gate_off`: the gate has no price today, so there is nothing to split;
- an earner without a `progress_source`.

A bad row among good rows is skipped, not fatal.

## Not credits

A `progress` row has `amount` 0 and its own kind. `done_today`, `credit_units`,
`first_credit_at` and `maturity` never see it, so it cannot earn a bonus, mature
a gate or start a penalty.

## Open question

What a paid review pays when no progress row exists is unchanged (the full 20
minutes, today's rule); kuhy has not decided otherwise.
