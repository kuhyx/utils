"""Shared plumbing for the relay tests: a fake claude, a fake probe, a client.

The relay runs in-process with its real threads (coverage sees it), on port
0, with the 3 s pace and the minute between probes injected away. The
LeetCode guard's data dir is redirected into the test's tmp dir and seeded
(`guard_digest`), so "byte-identical afterwards" is checked without racing
the live harvester on the developer's real files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
from http.client import HTTPConnection
import itertools
import json
from pathlib import Path
import time
from typing import TYPE_CHECKING, Any

from leetcode_coach.relay.app import Relay
from leetcode_coach.relay.coach import Deps
from leetcode_coach.relay.probe import AcceptedProbe
from leetcode_coach.tests._relay_statements import MISSING_NUMBER
from leetcode_guard import _constants
from leetcode_guard._submissions import AcSubmission, ProbeStatus, SolveProbe

if TYPE_CHECKING:
    import pytest

FAKE_CLAUDE = Path(__file__).with_name("_fake_claude.py")
DEV = "3f2a7c1e-9b4d-4e6f-8a1b-2c3d4e5f6a7b"
_RIDS = itertools.count(1)


def rid() -> str:
    """A fresh ULID-shaped request id."""
    return f"01JAXY{next(_RIDS):020d}"


def fake_claude(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **script: list[dict[str, Any]]
) -> Path:
    """Point ``LEETCODE_CLAUDE_BIN`` at the scripted fake; its directory."""
    root = tmp_path / "fake-claude"
    root.mkdir(exist_ok=True)
    (root / "calls.jsonl").write_text("", encoding="utf-8")
    (root / "script.json").write_text(json.dumps(script), encoding="utf-8")
    monkeypatch.setenv("LEETCODE_CLAUDE_BIN", str(FAKE_CLAUDE))
    monkeypatch.setenv("FAKE_CLAUDE_DIR", str(root))
    return root


def calls(root: Path) -> list[dict[str, Any]]:
    """Every call the fake claude answered."""
    lines = (root / "calls.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


@dataclass
class FakeProbe:
    """``fetch_recent_ac`` as a switch: unusable, nothing, or an Accepted."""

    status: str = "nothing"
    timestamp_s: int = 0
    calls: int = 0

    def __call__(self) -> SolveProbe:
        self.calls += 1
        if self.status == "unusable":
            return SolveProbe(ProbeStatus.UNVERIFIABLE, (), "session expired")
        rows = (
            (
                AcSubmission(
                    "1", "Missing Number", "missing-number", self.timestamp_s, "js"
                ),
            )
            if self.status == "accepted"
            else ()
        )
        return SolveProbe(ProbeStatus.OK, rows, "ok")


@dataclass
class Clock:
    """A monotonic clock the test moves (the probe's minute)."""

    now: float = 1000.0

    def __call__(self) -> float:
        return self.now


@dataclass
class Rig:
    """One relay and what drives it."""

    relay: Relay
    probe: FakeProbe
    clock: Clock
    sessions: Path
    extra: dict[str, Any] = field(default_factory=dict)


def make_rig(tmp_path: Path, *, start: bool = True, **deps: Any) -> Rig:
    """A relay on port 0 with fake fetch/probe and dry-run cards.

    ``heartbeat_s`` / ``rescan_s`` / ``pace_s`` go to the `Relay`, the rest to `Deps`.
    """
    timing = {
        k: deps.pop(k) for k in ("heartbeat_s", "rescan_s", "pace_s") if k in deps
    }
    probe, clock = FakeProbe(), Clock()
    base: dict[str, Any] = {
        "state_dir": tmp_path / "relay",
        "fetch": lambda _slug: ("Missing Number", MISSING_NUMBER),
        "probe": AcceptedProbe(probe, monotonic=clock),
        "cards_dry_run": True,
    }
    relay = Relay(
        Deps(**(base | deps)), port=0, tick_s=0.02, **({"pace_s": 0.0} | timing)
    )
    if start:
        relay.start()
    return Rig(relay, probe, clock, tmp_path / "sessions")


def http(rig: Rig, method: str, path: str, payload: object = None) -> tuple[int, Any]:
    """One loopback call; ``(status, decoded body)``."""
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
    headers = {} if body is None else {"Content-Type": "application/json"}
    conn = HTTPConnection("127.0.0.1", rig.relay.port, timeout=10)
    try:
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        return resp.status, json.loads(resp.read())
    finally:
        conn.close()


def call(rig: Rig, kind: str, **body: object) -> dict[str, Any]:
    """Send one request and poll until its result (what the app does)."""
    rid_ = rid()
    status, got = http(
        rig,
        "POST",
        "/coach/requests",
        {"rid": rid_, "kind": kind, "dev": DEV, "body": body},
    )
    if status == 200:
        return dict(got)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        _status, polled = http(rig, "GET", f"/coach/requests/{rid_}")
        if polled["result"] is not None:
            return dict(polled["result"])
        time.sleep(0.01)
    msg = f"no result for {kind}"
    raise AssertionError(msg)


def wait_for(check: Any, timeout: float = 5.0) -> Any:
    """Poll `check` until it returns something truthy."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if got := check():
            return got
        time.sleep(0.01)
    msg = "condition never held"
    raise AssertionError(msg)


def guard_digest() -> str:
    """A hash of every file under the (redirected) guard data dir."""
    digest = hashlib.sha256()
    root = Path(_constants.DATA_DIR)
    for path in sorted(root.rglob("*")):
        digest.update(str(path.relative_to(root)).encode())
        if path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


def seed_guard() -> None:
    """Put a ledger and caches where the guard would read them."""
    root = Path(_constants.DATA_DIR)
    (root / "ledger.json").write_text(
        '{"entries": [{"k": "credit:1"}]}', encoding="utf-8"
    )
    (root / "pool_cache.json").write_text("{}", encoding="utf-8")
