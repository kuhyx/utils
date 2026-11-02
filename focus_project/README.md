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
more than 120 s ahead (ValueError). `end_project(id, day)` rejects a past `day`
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
Open the work: `python3 -m focus_project.open [--no-site]` (tutor focus screen, `work_url`).
Install: `./install.sh` (stdlib only, editable user install for `/usr/bin/python3`).
