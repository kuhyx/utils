# holds

Declared time-boxed holds (contract v1): while a hold is active every gate
(focus-guard, diet-guard, screen-locker prompts) stands down so the PC stays
usable, e.g. for a proctored test. Stdlib only; gates import it from the system python.

```python
import holds

holds.active(now=None)        # Hold | None  (corrupt file -> None, logged: fail closed)
holds.covers("diet-guard")    # bool; v1: every gate
holds.next_change(now=None)   # datetime | None: active hold's end, else next start
holds.add(start, end, "reason of 10+ chars")   # raises HoldsError on a ratchet breach
holds.remove(hold_id)         # only before it starts
```

Ratchet (R11): each hold <= 15 h, <= 3 per ISO week (by start), start >= now + 30 min,
reason >= 10 chars, no overlaps, whole-minute times, existing holds are never edited.
Data: `$HOLDS_DATA` or `~/.local/share/holds/holds.json`, local naive times.
Install: `./install.sh` (editable, `/usr/bin/python3`). Tests: `python3 -m pytest`.
