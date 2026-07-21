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
VT-disable). Each axis (`overrideredirect`, `grab`, `disable_vt`,
`grab_retry_ms`) can be set explicitly to reproduce a consumer's exact prior
behavior where it diverges from the preset.

`gatelock.log_integrity` ports the HMAC-signed state module used by all three
projects; `DEFAULT_HMAC_KEY_FILE` (`/etc/workout-locker/hmac.key`) is
unchanged so existing signed history keeps verifying.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest
pre-commit install && pre-commit install --hook-type pre-push
```
