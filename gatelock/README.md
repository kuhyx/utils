# gatelock

Shared fullscreen lock-window + HMAC log-integrity backend, extracted from
three personal automation tools that each independently implemented "lock the
screen with a blocking overlay until a condition is met":
[diet_guard](https://github.com/kuhyx/testsAndMisc/tree/main/python_pkg/diet_guard),
[wake_alarm](https://github.com/kuhyx/testsAndMisc/tree/main/python_pkg/wake_alarm),
and [screen-locker](https://github.com/kuhyx/screen-locker).

## Why

All three reimplemented the same tkinter fullscreen mechanics (overrideredirect,
input grab, VT-switch disable) at different levels of maturity, and the
HMAC-signed-state module had already been hand-copied between two of them
because they live in separate repos. `gatelock` is the one place that logic
now lives.

## Install

```bash
pip install "gatelock @ git+https://github.com/kuhyx/utils@gatelock-v0.1.1#subdirectory=gatelock"
```

## Usage

```python
import tkinter as tk
from gatelock import GateRoot, LockConfig, LockWindow

class MyGate:
    def __init__(self, *, demo_mode: bool) -> None:
        self.root = GateRoot()
        self.root.on_callback_error = self._handle_callback_error
        config = LockConfig(mode="soft" if demo_mode else "hard")
        self._lock = LockWindow(self.root, config, hooks=self)
        self._lock.setup()
        # ... build your widgets ...
        self._lock.grab_input()

    def on_focus_ready(self) -> None:
        self.my_entry.focus_force()

    def on_callback_error(self) -> None:
        self.close()

    def on_close(self) -> None:
        ...  # release any hardware/state held while locked

    def close(self) -> None:
        self._lock.close()

    def run(self) -> None:
        self._lock.run()
```

`LockConfig`'s `mode` preset bundles the common combination ("soft" = topmost
only, typeable, WM-escapable; "hard" = overrideredirect + global grab +
VT-disable). `overrideredirect` and the `grab=GrabPolicy(kind=..., disable_vt=...,
retry_ms=...)` axes can be set explicitly to reproduce a consumer's exact prior
behavior where it diverges from the preset. Colours, type scale and spacing are
the `palette`, `typography` and `spacing` records (`gatelock.LockPalette` etc.),
overridden as a unit.

`gatelock.log_integrity` ports the HMAC-signed state module used by all three
projects; `DEFAULT_HMAC_KEY_FILE` (`/etc/workout-locker/hmac.key`) is
unchanged so existing signed history keeps verifying.

`gatelock.morning_session.morning_skip` is the one reader of wake-alarm's
signed `morning_session.json` (the wake-early carrot: no lock until the signed
`exempt_until`, 11:00 for a morning completed in time). screen-locker,
leetcode-guard and book-guard all call it; the policy itself stays in
wake-alarm. The arming run waits up to 180 s for a freshly booted PC's
refresher (status paths never wait). Path and retry budget are arguments so
each consumer's tests keep redirecting their own constant.

`gatelock.corner_strip` is the top-right always-on-top status strip for a gate
that is stood down but not done (`build_corner_strip`, `CornerStrip`,
`StripContent`, `corner_rect`, `corner_geometry`). It never grabs input; its
tick ends when the owner's `supply` returns `None`.

`gatelock.watch_credit(root, paths, is_done, on_credit, poll_ms=3000)` lets an
open lock window notice a credit that landed while it was up (a workout or meal
logged elsewhere). One `stat` per path per poll on the Tk `after` loop; the
owner's `is_done()` runs only on the first poll and when a path's (mtime, size,
inode) changed; True calls `on_credit` (the window's normal close) and stops.
A raising `is_done`/`on_credit` or an unreadable path is logged and retried
(fail closed). Pass `poll_ms` of 3000 or less: an open window should notice
inside ~10 s. Generalises screen-locker's `_credit_watch`.

`gatelock.night_lockdown.evening_lockdown_today` answers "has tonight's
evening night-lockdown already happened?" from night-lockdown's
`/var/lib/night-lockdown/locked_at_epoch` (local date today, local time
>= 12:00; the 04:01 morning re-lock does not count). Earner gates
(screen-locker's workout lock, leetcode-guard, book-guard) opt in and do not
re-arm for the rest of such a day; diet-guard does not. Missing or garbage
means "no lockdown" (garbage warns), so the gate locks as before.

`gatelock.held_grabs(claims_dir=None) -> tuple[Claim, ...]` answers "is a
locker's X grab ACTUALLY held right now?": live claims (flock-proved) whose
`grab_held` is true and whose declared grab is not `none`. `grab_held` turns
true only after `grab_set`/`grab_set_global` succeeded, follows each recovery
tick, and is cleared/restored around a deliberate release via
`LockWindow.report_grab_held(held=...)` (or `Arbiter.set_grab_held`) --
leetcode-guard's study mode. It is rewritten in place under the owner's flock.
A claim from a pre-0.11 writer has no key and reads as `grab != "none"`. Root
has no `XDG_RUNTIME_DIR`, so a root reader passes the user's dir
(`/run/user/1000/gatelock/claims`).

`LockWindow` yields to a system credential prompt that holds the X grab. If the
global grab stays unobtainable for more than 2 s AND a mapped window whose
WM_CLASS is in `gatelock._prompt_names.SYSTEM_PROMPT_CLASSES` (`gcr-prompter`,
`pinentry*`, polkit agents, ssh-askpass variants) is on screen, that prompt's
top-level window is raised above the lock and the lock's periodic re-raise
stops covering it while it stays mapped. The lock stays mapped, VT switching
stays disabled and the grab keeps being retried; once the grab is taken the lock
is back on top. Any other grab holder (a fullscreen game) never gets this.
`scripts/verify_prompt_yield.py` proves it on a private Xvfb (never `:0`).

Lockers that start together do not fight. `wait_for_turn` waits
`STARTUP_GRACE_SECONDS` (1.5 s) after `publish()` before its first check, so
simultaneous starters see each other. An armed lock also steps back (`_stepback`)
when a strictly higher-ranked, live claim that locks at least as firmly appears
later: it hides, releases the grab and its holder lock (the claim stays, so
lower ranks keep queueing), waits windowless, and re-arms fully once nothing
outranks it. `scripts/verify_all_lockers.py` checks this with five real
processes on a private Xvfb.

## Evening gate chain

`python3 -m gatelock.evening_chain pending|run` (0.15.0) runs book, then tutor,
then LeetCode in front of night lockdown. Needs the `evening` extra
(earned-time, freedays, sickdays); only this CLI imports them.

- `pending` prints the unpaid rungs. Exit 0 some rung is unpaid; 1 nothing
  to do (all paid, free day, sick day, or 23:00 and later); 2 could not
  check (unreadable ledger or key, any exception; stderr says why) -- it
  fails closed, so root enters lockdown. Reading and LeetCode use
  `earned_time.done_today`; the tutor is quota-based
  (`credit_units >= max_units`). Cheap: three small reads, root runs it
  every minute.
- `run` runs each unpaid rung's gate (`GATE_COMMANDS`, all `--production
  --evening`) and re-checks before each. A gate's exit 10
  (`EXIT_END_EVENING`) stops the chain with 0; 3 (`EXIT_NO_X`) exits 3; a
  gate killed at 23:00 or nothing left exits 0; a failing gate (or one that
  exits 0 with its rung still unpaid) is skipped, and two in a row exit 1.
- `RANK_EVENING_GATE` = 150 sits between the screen-locker and diet-guard.
- `systemd/evening-gates.service` is the user unit root starts;
  `install_evening_gates.sh` copies it and reloads, and never enables it.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest
pre-commit install && pre-commit install --hook-type pre-push
```
