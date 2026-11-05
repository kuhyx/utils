"""One OmniRoute gateway: container, volume, port, lock and state, read at call time."""

from __future__ import annotations

import fcntl
import json
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

REPO = "diegosouzapw/omniroute"
DEFAULT_IMAGE = f"{REPO}:3.8.52-web"
STABLE_TAG = re.compile(r"^(\d+)\.(\d+)\.(\d+)-web$")


@dataclass(frozen=True)
class Config:
    """One gateway instance (live: omniroute on 20128)."""

    name: str
    volume: str
    port: int
    base_url: str
    conf_dir: Path
    state_dir: Path
    backup_dir: Path
    signal_env: Path

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Config:
        """Read OMNIROUTE_NAME / _VOLUME / _PORT / _SIGNAL_ENV and HOME."""
        env = dict(os.environ) if env is None else env
        home = Path(env.get("HOME", str(Path.home())))
        name = env.get("OMNIROUTE_NAME", "omniroute")
        port = int(env.get("OMNIROUTE_PORT", "20128"))
        signal = env.get("OMNIROUTE_SIGNAL_ENV", str(home / "src/signal-bot/.env"))
        return cls(
            name=name,
            volume=env.get("OMNIROUTE_VOLUME", "omniroute-data"),
            port=port,
            base_url=f"http://127.0.0.1:{port}",
            conf_dir=home / ".config/omniroute",
            state_dir=home / ".local/state/omniroute-gateway" / name,
            backup_dir=home / "data/backups/omniroute" / name,
            signal_env=Path(signal),
        )

    def image(self) -> str:
        """Return the pinned image, or the repo default before any update."""
        try:
            pinned = (self.state_dir / "image").read_text().strip()
        except FileNotFoundError:
            return DEFAULT_IMAGE
        return pinned or DEFAULT_IMAGE


def version(tag: str) -> tuple[int, int, int] | None:
    """Return (major, minor, patch) of a stable '-web' tag or image ref, else None."""
    match = STABLE_TAG.match(tag.rsplit(":", 1)[-1])
    if not match:
        return None
    major, minor, patch = (int(g) for g in match.groups())
    return major, minor, patch


@contextmanager
def locked(cfg: Config, *, blocking: bool) -> Iterator[bool]:
    """Hold the instance lock; yields False when non-blocking and already held."""
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    with (cfg.state_dir / "lock").open("w") as handle:
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        try:
            fcntl.flock(handle, flags)
        except BlockingIOError:
            yield False
            return
        yield True


def load_state(cfg: Config) -> dict[str, Any]:
    """Return alert state; empty when missing or unreadable."""
    try:
        data = json.loads((cfg.state_dir / "alert.json").read_text())
    except OSError, json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def save_state(cfg: Config, data: dict[str, Any], image: str | None = None) -> None:
    """Persist alert state, and the newly running image when given."""
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    (cfg.state_dir / "alert.json").write_text(json.dumps(data, sort_keys=True))
    if image:
        (cfg.state_dir / "image").write_text(f"{image}\n")
