"""Weekly: back up the data volume, then move to the newest stable '-web' tag.

A new tag must pass the health check (a real chat answer) or the volume is
restored and the old image put back. Exit: 0 current / updated, 1 failed.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from omniroute_offload import _gw_api as api
from omniroute_offload import _gw_combo as combo
from omniroute_offload import _gw_config as gwc
from omniroute_offload import _gw_docker as dock
from omniroute_offload import _gw_health as health
from omniroute_offload import _gw_notify as note

if TYPE_CHECKING:
    from pathlib import Path

    from omniroute_offload._gw_config import Config

HUB = f"https://hub.docker.com/v2/repositories/{gwc.REPO}/tags?page_size=100&ordering=last_updated"


def latest_image() -> str:
    """Return the newest stable '-web' image on Docker Hub."""
    tags = [str(t.get("name", "")) for t in api.call(HUB, timeout=30)["results"]]
    stable = [t for t in tags if gwc.version(t)]
    if not stable:
        msg = "no stable -web tag on Docker Hub"
        raise api.ApiError(msg)
    return f"{gwc.REPO}:{max(stable, key=lambda t: gwc.version(t) or (0, 0, 0))}"


def _switch(cfg: Config, image: str) -> health.Verdict:
    dock.recreate(cfg, image, health.secret(cfg, "admin_password"))
    if not health.wait_up(cfg):
        return health.Verdict("down", f"{image} API never came up")
    return health.check(cfg, datetime.now(UTC))


def _rollback(cfg: Config, image: str, archive: Path) -> None:
    if dock.status(cfg) is not None:
        dock.docker("stop", "-t", str(dock.STOP_TIMEOUT_S), cfg.name)
    dock.restore(cfg, image, archive)
    dock.recreate(cfg, image, health.secret(cfg, "admin_password"))
    health.wait_up(cfg)


def _upgrade(cfg: Config, current: str, archive: Path) -> int:
    latest = latest_image()
    have, newest = gwc.version(current), gwc.version(latest)
    if have is None or newest is None or newest <= have:
        print(f"up to date: {current} (newest {latest})", file=sys.stderr)
        return 0
    print(f"updating {current} -> {latest}", file=sys.stderr)
    try:
        dock.pull(latest)
        verdict = _switch(cfg, latest)
    except (dock.DockerError, api.ApiError, OSError) as err:
        verdict = health.Verdict("down", str(err))
    if verdict.state == "ok":
        gwc.save_state(cfg, gwc.load_state(cfg), image=latest)
        combo.refresh(cfg)
        sent = note.notify(cfg, f"updated {current} -> {latest}", urgency="low")
        return 0 if sent else 1
    _rollback(cfg, current, archive)
    note.notify(
        cfg,
        f"update to {latest} failed ({verdict.detail}); rolled back to {current}",
        urgency="critical",
    )
    return 1


def run(cfg: Config) -> int:
    """Back up, then update if a newer tag exists, under the instance lock."""
    with gwc.locked(cfg, blocking=True):
        current = cfg.image()
        try:
            archive = dock.backup(cfg, current.rsplit(":", 1)[-1])
            print(f"backup: {archive}", file=sys.stderr)
            return _upgrade(cfg, current, archive)
        except (dock.DockerError, api.ApiError, OSError) as err:
            note.notify(cfg, f"update job failed: {err}", urgency="critical")
            return 1
