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
Open the work: `python3 -m focus_project.open [--no-site]` (tutor focus screen, `work_url`).
Install: `./install.sh` (stdlib only, editable user install for `/usr/bin/python3`).
