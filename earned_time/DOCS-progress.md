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

`done` is capped at `target`. Among the matching rows that verify, the last one
in file order wins, and `done` and `target` both come from that one row. A gate
can re-derive its target within a day (book-guard does), so mixing rows would
pair a stale target with a new done. The rule reads neither `created_at` nor
`device` (the workout ledger writes neither). A later row that fails any check
above is skipped, so the last good row wins; no good row is `None`. A signed
row copied to the end of the file wins as it is: the key is the trust, not the
position.

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

## The review: no row, no pay (from `REVIEW_PROGRESS_FROM`)

kuhy's rule (2026-11-22): the review top-up pays in equal slices, `bonus * done
// target`, the writer freezing the target at the day's first review. From
`REVIEW_PROGRESS_FROM` (2026-11-24, the day after the 2026-11-23 release; a rule
that lowers pay never lands on its deploy day) the review differs from the other
earners:

- a credited review (a yes) pays only by its row: `done` of `target` of 20
  minutes, never more than 20; the gaming twin is 0 as ever, and a sick day adds
  the same minutes on top of 20:00;
- a credited review with no row pays **0**, not the flat 20, and logs a warning;
- a row that fails verification (bad signature, edited, wrong day or source,
  unreadable numbers) is no row, so it pays 0 too. This is deliberate: fail
  closed, visible in the log, never a flat 20 for a row nobody can vouch for;
- a no or `None` pays 0 whatever a row says: the guard's accepted submission, not
  the row, is the evidence that a review happened (`DOCS-review.md`).

Before `REVIEW_PROGRESS_FROM` the review pays as in 0.23.0 (a yes pays 20, a no
0) and ignores every progress row.

## One derivation: `term_for`

`term_for(earner, day, *, answer, progress=None) -> Term` is the only place an
earner's pay for a day is derived, and `resolve` builds every one of its terms
through it. A consumer that prices one earner (the screen-locker's live pass)
reads the row with `read_progress` and calls it; it reads `shutdown_minutes`
and `gaming_minutes` off the `Term`. **Consumers never re-derive a share**: the
review's dated rule, the ladder rung, the floor and the cap at full all live
here, and a local `full * done // target` goes stale the day a rule changes.

```python
fact = earned_time.read_progress(earner, ledger, key_file, day, gate_off=off)
pay = earned_time.term_for(earner, day, answer=answer, progress=fact).shutdown_minutes
```

`answer` is the unit count (`True`/`False` are 1/0) or `None`; `progress` is the
verified row or `None`. A test pins that the two always agree for every earner,
answer, row and day either side of `REVIEW_PROGRESS_FROM`.

## Not credits

A `progress` row has `amount` 0 and its own kind. `done_today`, `credit_units`,
`first_credit_at` and `maturity` never see it, so it cannot earn a bonus, mature
a gate or start a penalty.
