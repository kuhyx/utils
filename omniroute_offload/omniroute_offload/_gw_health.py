"""Health = a real completion through free-best, then the fix ladder.

Ladder on "down": 1) restart (or recreate) the container when it or its API is
dead, at most once per RESTART_GAP; 2) reactivate combo providers marked
failed whose cooldown already ended; 3) notify once per outage. Every provider
cooling down is "degraded", not down: no restart, one notice per day.
Exit: 0 ok / degraded / fixed, 1 still down.
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from omniroute_offload import _gw_api as api
from omniroute_offload import _gw_config as gwc
from omniroute_offload import _gw_docker as dock
from omniroute_offload import _gw_notify as note

if TYPE_CHECKING:
    from omniroute_offload._gw_config import Config

RESTART_GAP = timedelta(minutes=30)


@dataclass(frozen=True)
class Verdict:
    """ok | degraded | down, with the reason."""

    state: str
    detail: str


def secret(cfg: Config, name: str) -> str:
    """Read a stripped file from conf_dir (admin_password, api_key)."""
    return (cfg.conf_dir / name).read_text().strip()


def wait_up(cfg: Config, seconds: float = 90) -> bool:
    """Poll the API until it answers or `seconds` pass."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if api.alive(cfg):
            return True
        time.sleep(2)
    return api.alive(cfg)


def _members(conns: list[dict[str, Any]], members: set[str]) -> list[dict[str, Any]]:
    return [c for c in conns if c.get("provider") in members and c.get("isActive")]


def _cooling(conn: dict[str, Any], now: datetime) -> bool:
    until = api.cooldown_until(conn)
    return until is not None and until > now


def check(cfg: Config, now: datetime) -> Verdict:
    """Classify the gateway by one real chat call plus provider state."""
    if not api.alive(cfg):
        return Verdict("down", "API not answering")
    try:
        api.chat(cfg, secret(cfg, "api_key"))
    except (api.ApiError, OSError) as err:
        detail = f"chat failed: {err}"
    else:
        return Verdict("ok", "chat answered")
    try:
        admin = api.Admin(cfg, secret(cfg, "admin_password"))
        conns = _members(admin.providers(), admin.combo_members())
    except (api.ApiError, OSError) as err:
        return Verdict("down", f"{detail}; admin API: {err}")
    if conns and all(_cooling(c, now) for c in conns):
        return Verdict("degraded", f"all {len(conns)} combo providers cooling down")
    return Verdict("down", detail)


def _restart(cfg: Config, state: dict[str, Any], now: datetime) -> None:
    last = state.get("last_restart")
    try:
        recent = now - datetime.fromisoformat(str(last)) < RESTART_GAP
    except TypeError, ValueError:
        recent = False
    if recent:
        print(f"restart skipped: last one at {last}", file=sys.stderr)
        return
    state["last_restart"] = now.isoformat()
    if dock.status(cfg) is None:
        print("container missing: recreating", file=sys.stderr)
        dock.recreate(cfg, cfg.image(), secret(cfg, "admin_password"))
    else:
        print("restarting container", file=sys.stderr)
        dock.restart(cfg)
    wait_up(cfg)


def _reactivate(cfg: Config, now: datetime) -> int:
    admin = api.Admin(cfg, secret(cfg, "admin_password"))
    stuck = [
        c
        for c in _members(admin.providers(), admin.combo_members())
        if c.get("testStatus") != "active" and not _cooling(c, now)
    ]
    for conn in stuck:
        print(f"reactivating {conn.get('provider')}", file=sys.stderr)
        admin.reactivate(str(conn["id"]))
    return len(stuck)


def heal(cfg: Config, state: dict[str, Any], now: datetime) -> Verdict:
    """Check, then walk ladder steps 1-2 while still down."""
    verdict = check(cfg, now)
    print(f"check: {verdict.state}: {verdict.detail}", file=sys.stderr)
    if verdict.state == "down" and (
        dock.status(cfg) != "running" or not api.alive(cfg)
    ):
        _restart(cfg, state, now)
        verdict = check(cfg, now)
        print(f"after restart: {verdict.state}: {verdict.detail}", file=sys.stderr)
    if verdict.state == "down" and api.alive(cfg) and _reactivate(cfg, now):
        verdict = check(cfg, now)
        print(f"after reactivate: {verdict.state}: {verdict.detail}", file=sys.stderr)
    return verdict


def _report(cfg: Config, state: dict[str, Any], verdict: Verdict, now: datetime) -> int:
    if verdict.state == "ok":
        if state.pop("down_since", None):
            sent = note.notify(cfg, "recovered: free-best answers again", urgency="low")
            return 0 if sent else 1
        return 0
    if verdict.state == "degraded":
        today = now.date().isoformat()
        if state.get("degraded_day") != today:
            state["degraded_day"] = today
            sent = note.notify(cfg, f"degraded: {verdict.detail}", urgency="low")
            return 0 if sent else 1
        return 0
    if not state.get("down_since"):
        state["down_since"] = now.isoformat()
        note.notify(cfg, f"DOWN after auto-fix: {verdict.detail}", urgency="critical")
    return 1


def run(cfg: Config, now: datetime | None = None) -> int:
    """One health tick under the instance lock (skips while an update runs)."""
    now = now or datetime.now(UTC)
    with gwc.locked(cfg, blocking=False) as got:
        if not got:
            print("update in progress: health skipped", file=sys.stderr)
            return 0
        state = gwc.load_state(cfg)
        try:
            verdict = heal(cfg, state, now)
        except (api.ApiError, dock.DockerError, OSError) as err:
            verdict = Verdict("down", f"fix ladder failed: {err}")
        code = _report(cfg, state, verdict, now)
        gwc.save_state(cfg, state)
        print(f"result: {verdict.state}", file=sys.stderr)
        return code
