# Copyright (c) 2026 Krzysztof Rudnicki
"""The local record of every report ingested, grouped by app and signature.

It is the source of truth once RTDB entries and spool lines are consumed:
``seen`` makes a re-read count nothing twice, and each signature keeps its
count, first and last time, newest build and its resolution. :func:`report`
turns one app's records into the todoImplementer ``app-error`` contract
(``contracts/app-error.schema.json``, ``report``).

Resolve and reopen: ``resolve`` stores the time and the newest build seen. A
later report reopens the error only when it is a regression: a newer build
when both sides know the build, else a report made after the resolve.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
from typing import TYPE_CHECKING, NotRequired, TypedDict, cast

from app_errors.signature import SLOW_KIND, mark_of, signature, strings, top_frame

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

#: Entry ids remembered for dedup (oldest dropped first).
MAX_SEEN = 5000
#: An app name the board accepts (the contract's ``app`` pattern).
APP_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_REPO = re.compile(r"^[^/\s]+/[^/\s]+$")
#: The owner guessed for an app whose report names no repo and has no checkout.
OWNER = "kuhyx"


def guess_repo(app: str) -> str:
    """Return ``OWNER/app``: the fallback when nothing better names the repo."""
    return f"{OWNER}/{app}"


class Resolved(TypedDict):
    """When the error was marked fixed, and the newest build seen then."""

    at: str
    build: int


class Rec(TypedDict):
    """Everything known about one signature of one app."""

    signature: str
    repo: str
    kind: str
    message: str
    top_frame: str | None
    route: str | None
    count: int
    first_seen: str
    last_seen: str
    build: int
    version_name: str | None
    longest_ms: NotRequired[int]
    resolved: Resolved | None


class State(TypedDict):
    """The whole state file."""

    version: int
    seen: dict[str, str]
    apps: dict[str, dict[str, Rec]]


def empty() -> State:
    """Return a state that knows nothing."""
    return {"version": 1, "seen": {}, "apps": {}}


def load(path: Path) -> State:
    """Return the state at ``path``; empty when missing or unreadable."""
    try:
        data = json.loads(path.read_text())
    except OSError, ValueError:
        return empty()
    if not isinstance(data, dict) or data.get("version") != 1:
        return empty()
    return cast("State", data)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.stem}-")
    with os.fdopen(fd, "w") as f:
        f.write(text)
    Path(tmp).replace(path)


def save(path: Path, state: State) -> None:
    """Write ``state`` atomically (temp file + rename)."""
    _atomic_write(path, json.dumps(state, indent=1, sort_keys=True))


def _int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _reopens(resolved: Resolved, at: str, build: int) -> bool:
    if build and resolved["build"]:
        return build > resolved["build"]
    return at > resolved["at"]


def merge(
    state: State,
    app: str,
    entry_id: str,
    raw: object,
    *,
    repo_of: Callable[[str], str] = guess_repo,
) -> bool:
    """Count one report ``raw`` of ``app`` under its signature; False when seen or not a report.

    A new record takes the report's ``repo``, else ``repo_of(app)``.
    """
    if not isinstance(raw, dict):
        return False
    entry = cast("Mapping[str, object]", raw)
    at, kind = entry.get("at"), entry.get("kind")
    if not isinstance(at, str) or not at or not isinstance(kind, str) or not kind:
        return False
    key = f"{app}/{entry_id}"
    if key in state["seen"]:
        return False
    state["seen"][key] = at
    while len(state["seen"]) > MAX_SEEN:
        del state["seen"][next(iter(state["seen"]))]
    sig = signature(entry, app=app)
    build = _int(entry.get("build"))
    recs = state["apps"].setdefault(app, {})
    rec = recs.get(sig.id)
    if rec is None:
        repo = _str(entry.get("repo"))
        rec = recs[sig.id] = {
            "signature": sig.id,
            "repo": repo if repo and _REPO.match(repo) else repo_of(app),
            "kind": kind,
            "message": sig.message,
            "top_frame": top_frame(strings(entry.get("stack")), mark_of(entry, app)),
            "route": _str(entry.get("route")),
            "count": 0,
            "first_seen": at,
            "last_seen": at,
            "build": 0,
            "version_name": None,
            "resolved": None,
        }
    rec["count"] += 1
    rec["first_seen"] = min(rec["first_seen"], at)
    rec["last_seen"] = max(rec["last_seen"], at)
    if build >= rec["build"]:
        rec["build"] = build
        rec["version_name"] = _str(entry.get("version")) or rec["version_name"]
    if kind == SLOW_KIND:
        rec["longest_ms"] = max(rec.get("longest_ms", 0), _int(entry.get("durationMs")))
    resolved = rec["resolved"]
    if resolved is not None and _reopens(resolved, at, build):
        rec["resolved"] = None
    return True


def resolve(state: State, app: str, sig: str, *, now: str) -> bool:
    """Mark ``app``'s ``sig`` fixed as of ``now``; False when there is no such error."""
    rec = state["apps"].get(app, {}).get(sig)
    if rec is None:
        return False
    rec["resolved"] = {"at": now, "build": rec["build"]}
    return True


def _detail(rec: Rec) -> str | None:
    route = f"route {rec['route']}" if rec["route"] else None
    if rec["kind"] == SLOW_KIND:
        longest = f"longest wait {rec.get('longest_ms', 0)} ms"
        return f"{longest}, {route}" if route else longest
    return route


def report(state: State, app: str) -> dict[str, object]:
    """Return ``app``'s records as a contract ``report``."""
    errors = [
        {
            "app": app,
            "repo": rec["repo"],
            "signature": rec["signature"],
            "kind": rec["kind"],
            "message": rec["message"],
            "top_frame": rec["top_frame"],
            "count": rec["count"],
            "first_seen": rec["first_seen"],
            "last_seen": rec["last_seen"],
            "build": rec["build"],
            "version_name": rec["version_name"],
            "detail": _detail(rec),
            "open": rec["resolved"] is None,
        }
        for rec in sorted(state["apps"].get(app, {}).values(), key=lambda r: r["signature"])
    ]
    return {"version": 1, "errors": errors}


def write_reports(folder: Path, state: State) -> list[Path]:
    """Write ``<folder>/<app>.json`` for every app with records; return the paths."""
    written = []
    for app in sorted(state["apps"]):
        path = folder / f"{app}.json"
        _atomic_write(path, json.dumps(report(state, app), indent=1))
        written.append(path)
    return written
