"""Per-app state file and artefact directory under ~/data/claude-scratch/e2e/<app>/."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path


def artefact_root() -> Path:
    """``$FWD_ARTEFACTS`` or ~/data/claude-scratch/e2e (never /tmp: it is wiped)."""
    env = os.environ.get("FWD_ARTEFACTS")
    return Path(env) if env else Path.home() / "data" / "claude-scratch" / "e2e"


def stamp() -> str:
    """Sortable timestamp for artefact names."""
    now = time.time()
    return (
        time.strftime("%Y%m%d-%H%M%S", time.localtime(now))
        + f"-{int(now * 1000) % 1000:03d}"
    )


@dataclass(frozen=True)
class State:
    """What ``start`` launched, so later verbs attach to the same browser."""

    unit: str
    cdp_port: int
    url: str
    profile: str


def state_path(root: Path, app: str) -> Path:
    """Where ``app``'s state lives."""
    return root / app / "state.json"


def load(root: Path, app: str) -> State | None:
    """The saved state, or None before the first start / after stop."""
    path = state_path(root, app)
    if not path.is_file():
        return None
    return State(**json.loads(path.read_text()))


def save(root: Path, app: str, state: State) -> None:
    """Persist state (creates the app's artefact dir)."""
    path = state_path(root, app)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(state), indent=2) + "\n")


def clear(root: Path, app: str) -> None:
    """Forget the state after stop."""
    state_path(root, app).unlink(missing_ok=True)
