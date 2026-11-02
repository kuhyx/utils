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
Install: `./install.sh` (stdlib only, editable user install for `/usr/bin/python3`).
