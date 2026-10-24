"""Verbs on one attached page: read the tree, send real input, capture output."""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flutter_web_drive import semantics
from flutter_web_drive.cdp import Session
from flutter_web_drive.errors import EXIT_USAGE, DriveError
from flutter_web_drive.keys import KEYS
from flutter_web_drive.semantics import Node

POLL = 0.25


@dataclass(frozen=True)
class Clock:
    """Monotonic time + sleep, injectable so polling is testable."""

    now: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep


def poll_nodes(sess: Session) -> list[Node]:
    """Ask for semantics (idempotent) and read whatever nodes exist right now."""
    sess.evaluate(semantics.ENABLE_JS)
    return semantics.parse_nodes(sess.evaluate(semantics.COLLECT_JS))


def ensure_semantics(sess: Session, clock: Clock, timeout: float = 5.0) -> list[Node]:
    """Nodes once the semantics mirror is populated, or fail after ``timeout``."""
    deadline = clock.now() + timeout
    while True:
        nodes = poll_nodes(sess)
        if nodes:
            return nodes
        if clock.now() >= deadline:
            raise DriveError(
                "semantics",
                f"no Flutter semantics nodes after {timeout:g}s (not a Flutter page, or still loading?)",
            )
        clock.sleep(POLL)


def viewport(sess: Session) -> tuple[int, int]:
    """Layout viewport in CSS pixels (what screenshots and rects use)."""
    width, height = sess.evaluate(semantics.VIEWPORT_JS)
    return int(width), int(height)


def click_at(sess: Session, x: float, y: float) -> None:
    """A real left click: move, press, release, so Flutter's pointer path sees it."""
    sess.call("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
    for kind in ("mousePressed", "mouseReleased"):
        sess.call(
            "Input.dispatchMouseEvent", type=kind, x=x, y=y, button="left", clickCount=1
        )


def tap(sess: Session, clock: Clock, target: str, *, contains: bool = False) -> str:
    """Click the center of the best node labelled ``target``."""
    nodes = ensure_semantics(sess, clock)
    hits = semantics.find(nodes, target, contains=contains)
    if not hits:
        raise DriveError(
            "tap", f'no node labelled "{target}"; tappable: {semantics.hint(nodes)}'
        )
    best = hits[0]
    x, y = best.center
    width, height = viewport(sess)
    if not (0 <= x < width and 0 <= y < height):
        raise DriveError(
            "tap", f'"{best.one_line}" is off-screen at ({x:g}, {y:g}); scroll first'
        )
    click_at(sess, x, y)
    extra = f" ({len(hits)} matches; took the first)" if len(hits) > 1 else ""
    return f"tapped {semantics.describe(best)}{extra}"


def tap_xy(sess: Session, x: float, y: float) -> str:
    """Click at viewport coordinates."""
    click_at(sess, x, y)
    return f"tapped ({x:g}, {y:g})"


def insert_text(sess: Session, text: str) -> str:
    """Type into the focused field (never echoes the text back)."""
    if not sess.evaluate(semantics.FOCUS_JS):
        raise DriveError("text", "no focused text field; tap the field first")
    sess.call("Input.insertText", text=text)
    return f"inserted {len(text)} characters"


def press_key(sess: Session, name: str) -> str:
    """Key down + up for one named key."""
    if name not in KEYS:
        raise DriveError(
            "key", f"unknown key {name!r}; known: {', '.join(KEYS)}", EXIT_USAGE
        )
    key, code, vk, text = KEYS[name]
    down: dict[str, Any] = {
        "type": "keyDown",
        "key": key,
        "code": code,
        "windowsVirtualKeyCode": vk,
    }
    if text:
        down["text"] = text
    sess.call("Input.dispatchKeyEvent", **down)
    sess.call(
        "Input.dispatchKeyEvent",
        type="keyUp",
        key=key,
        code=code,
        windowsVirtualKeyCode=vk,
    )
    return f"pressed {name}"


def scroll(
    sess: Session, dx: float, dy: float, at: tuple[float, float] | None = None
) -> str:
    """Mouse-wheel by (dx, dy) at ``at`` (default: viewport center)."""
    if at is None:
        width, height = viewport(sess)
        at = (width / 2, height / 2)
    x, y = at
    sess.call(
        "Input.dispatchMouseEvent", type="mouseWheel", x=x, y=y, deltaX=dx, deltaY=dy
    )
    return f"scrolled ({dx:g}, {dy:g}) at ({x:g}, {y:g})"


def wait_for(
    sess: Session,
    clock: Clock,
    target: str,
    *,
    timeout: float,
    on_timeout: Callable[[], str],
    contains: bool = False,
    gone: bool = False,
    flag: str | None = None,
    row: str | None = None,
) -> str:
    """Poll until a node labelled ``target`` (carrying ``flag``) is present, or absent with ``gone``."""
    what = (
        f'"{target}"'
        + (f' in row "{row}"' if row else "")
        + (f" [{flag}]" if flag else "")
    )
    deadline = clock.now() + timeout
    while True:
        nodes = poll_nodes(sess)
        hits = semantics.find(
            semantics.in_row(nodes, row) if row else nodes, target, contains=contains
        )
        hits = [h for h in hits if flag is None or flag in h.flags]
        if hits and not gone:
            return f"found {semantics.describe(hits[0])}"
        if gone and not hits:
            return f"gone: {what}"
        if clock.now() >= deadline:
            state = "still present" if gone else "not present"
            raise DriveError(
                "wait",
                f"{what} {state} after {timeout:g}s; screenshot {on_timeout()}",
            )
        clock.sleep(POLL)


def screenshot(sess: Session, out: Path, min_colours: int = 0) -> str:
    """Write a PNG of the viewport; fail if it has fewer than ``min_colours`` colours."""
    data = sess.call("Page.captureScreenshot", format="png")["data"]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(base64.b64decode(data))
    stats = sess.evaluate(f"{semantics.IMAGE_STATS_FN}({json.dumps(data)})")
    colours = int(stats["colours"])
    summary = f"{out} {stats['w']}x{stats['h']} colours={colours} stddev={float(stats['stddev']):.1f}"
    if colours < min_colours:
        raise DriveError(
            "shot",
            f"screenshot looks blank ({colours} colours < {min_colours}): {summary}",
        )
    return summary


def evaluate(sess: Session, expr: str) -> str:
    """Run JS in the page and return its value as JSON."""
    return json.dumps(sess.evaluate(expr))


def _event_line(event: dict[str, Any]) -> tuple[str, str] | None:
    """(level, text) for console/log events worth reporting, else None."""
    method, params = event.get("method"), event.get("params", {})
    if method == "Runtime.consoleAPICalled" and params.get("type") in {
        "error",
        "assert",
        "warning",
    }:
        level = "warning" if params["type"] == "warning" else "error"
        args = " ".join(
            str(a.get("value", a.get("description", "")))
            for a in params.get("args", [])
        )
        return level, args
    if method == "Runtime.exceptionThrown":
        det = params.get("exceptionDetails", {})
        desc = det.get("exception", {}).get("description", "")
        return (
            "error",
            f"{det.get('text', 'exception')} {desc.splitlines()[0] if desc else ''}".strip(),
        )
    if method == "Log.entryAdded" and params.get("entry", {}).get("level") in {
        "error",
        "warning",
    }:
        return params["entry"]["level"], str(params["entry"].get("text", ""))
    return None


def console(
    sess: Session, limit: int = 20, *, warnings: bool = False
) -> tuple[str, int]:
    """Errors (and optionally warnings) since page load; chromium replays them on enable."""
    sess.call("Runtime.enable")
    sess.call("Log.enable")
    lines = [line for e in sess.drain(0.5) if (line := _event_line(e))]
    errors = sum(1 for level, _ in lines if level == "error")
    shown = [f"{lv}: {text}" for lv, text in lines if warnings or lv == "error"][
        -limit:
    ]
    return ("\n".join(shown) if shown else "no console errors"), errors
