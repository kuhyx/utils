# focus_project

Time-boxed focus projects ("until Thursday I prepare for X"). The active
project switches chosen gates off and defines a daily-minutes gate.

```python
import focus_project as fp

fp.stands_down("leetcode", today)   # gate in leetcode|book|reading|tutor; never raises
fp.active(today)                    # Project | None
fp.status(today)                    # dict for i3bar / GUIs
fp.record_activity("timer", "start")
```

Data: `$FOCUS_PROJECT_DATA` or `~/.local/share/focus_project/` (`projects.json`,
`activity.jsonl`). `minutes.py` is owned by the minutes/harvester agent.
Time rules: `minutes_for` clips every interval at "now" (an event stamped ahead of
the clock earns only once the clock reaches it); `record_activity` rejects a `ts`
more than 120 s ahead (ValueError). Timer segments (`start` -> `checkin` ... -> `stop`)
lapse after a 600 s gap; a `tutor`/`heartbeat` is a beat too (0.8.0: a graded check-in card
extends the open segment, never opens one). `end_project(id, day)` rejects a past `day`
(ValueError); today or later is fine. The harvester pays every project day of the
last 31 days, so late-synced events for older days are credited (idempotent).
Overtime carries over: own minutes past a day's target bank (max 60) and pay on the
next project day; the bank never crosses the project's end. `minutes_for(day)` is the
capped pay figure, `status(day)["minutes"]` the real count (121/120) with `carried_in`,
`carry_out`, `own_minutes`, `counted_minutes`. Carry ledger rows: `<project>-<YYYYMMDD>-carry`
(`detail.carry`), never over `daily_minutes` together with own rows.
Edits only ratchet (0.7.0): `update_project`/`apply_update(id, today=...)` never lowers
today's obligation. A lower `daily_minutes`/`unlock_minutes`, or a gate added to `replaces`,
on a started project holds from TOMORROW (a `history` row ends today with the old values,
`replaces_on(day)`/`daily_on`/`unlock_on` read it); a mixed edit defers as a whole. Raises,
gates removed and edits to a project that has not started hold from today.
`apply_update(...).effective_from` says which. `end` cannot be before today, so an edit never
uncovers today. A NEW project starting today may replace gates and set any targets: it is a
new obligation, not a reduction (but see the floor).
Floor (0.7.1, coordinator decision for kuhy): `daily_minutes >= 30 x replaced gates` (min 30; `book` = `reading`),
enforced on create and update (`daily_floor(replaces)`), so a day cannot be made cheap.
Backed timer (0.10.0, days from `BACKING_FROM` = 2026-11-08): a timer span earns only if a
same-project `tutor`/`sql_drills`/`leetcode` beat (or accepted submission) is in it, 5 min
before it, or bridges it (beats <= 20 min apart). `unbacked_minutes_for(day)` /
`status()["unbacked_minutes"]` show the rest. A beat backs only the spans it touches (the tutor chain makes a graded card back the whole stretch). Known gap: any coach turn backs.
Open the work: `python3 -m focus_project.open [--no-site]` (tutor focus screen, `work_url`).
Install: `./install.sh` (stdlib only, editable user install for `/usr/bin/python3`).

Interview prep (`kind="interview"`, 0.9): `create_project(..., kind="interview", test_at=, invite_url=, trips=, weekend_answers=)`;
`end` must be the test day. Budget: 30 min weekdays / 120 Sat-Sun (`daily_on`), exempt from `daily_floor`, unlock clamped.
Milestones are generated, never stored: `milestones(project, now)` -> `rules`, `trip_ask:<sat>`, `phone:<trip start>`, `mock`, `slot`
with states pending/done/missed/late_done/unknown. `owed_lock(now)` = earliest overdue uncompleted one (never on test day; wire it
after focus-guard's sick/free-day stand-down). `status(day)` gains `milestones` and `missed`.
Evidence is append-only (`evidence/<id>.jsonl` + copied files): `record_evidence(id, milestone, kind, value, file=, now=)`
(`file`, `tap`, `score`, `slot`, `slot_confirm`, tutor's `phone_check`). `add_trip` / `answer_weekend` only get stricter (ValueError).
`run_checks(id)` runs the `phone` source (reads the latest `phone_check` row) and latches changes; `register_source` swaps it.
