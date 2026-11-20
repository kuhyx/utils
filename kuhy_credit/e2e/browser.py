"""Headless chromium + a loopback file server, driven over CDP.

Shared by the web and Flutter-web E2Es. The browser never has a window and
never touches kuhy's display; window.open is replaced before any page script
runs, so "opening the website" only records the URL.
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from flutter_web_drive import cdp  # noqa: E402

CREDIT = json.loads((REPO / "kuhy_credit/credit.json").read_text())

STUB = """
window.__opened = [];
window.open = (url) => { window.__opened.push(String(url)); return null; };
"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def chromium() -> str:
    for cand in (os.environ.get("CHROMIUM", ""), "/usr/bin/chromium", "google-chrome", "chromium"):
        if cand and shutil.which(cand):
            return cand
    raise SystemExit("no chromium found (set CHROMIUM)")


def wait_for(probe, what: str, timeout: float = 20.0) -> Any:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        with contextlib.suppress(Exception):
            got = probe()
            if got:
                return got
        time.sleep(0.1)
    raise AssertionError(f"timed out waiting for {what}")


class Page:
    """One CDP page with mouse/keyboard helpers."""

    def __init__(self, sess: cdp.Session) -> None:
        self.s = sess

    def eval(self, expr: str) -> Any:
        return self.s.evaluate(expr)

    def click(self, x: float, y: float) -> None:
        for kind in ("mousePressed", "mouseReleased"):
            self.s.call(
                "Input.dispatchMouseEvent", type=kind, x=x, y=y, button="left", clickCount=1
            )
        time.sleep(0.15)

    def key(self, key: str, code: str, vk: int, text: str = "") -> None:
        """Press and release one key; ``text`` makes Enter/Space activate."""
        extra = {"text": text} if text else {}
        self.s.call(
            "Input.dispatchKeyEvent",
            type="keyDown" if text else "rawKeyDown",
            key=key,
            code=code,
            windowsVirtualKeyCode=vk,
            **extra,
        )
        self.s.call(
            "Input.dispatchKeyEvent", type="keyUp", key=key, code=code, windowsVirtualKeyCode=vk
        )
        time.sleep(0.15)

    def opened(self) -> list[str]:
        return list(self.eval("window.__opened"))

    def shot(self, path: Path) -> None:
        data = self.s.call("Page.captureScreenshot", format="png")["data"]
        path.write_bytes(base64.b64decode(data))

    def foreign_requests(self) -> list[str]:
        urls = [
            e["params"]["request"]["url"]
            for e in self.s.drain(0.3)
            if e.get("method") == "Network.requestWillBeSent"
        ]
        return [u for u in urls if not u.startswith(("http://127.0.0.1", "data:", "blob:"))]


@contextlib.contextmanager
def session(serve_dir: Path, size: str = "900,600") -> Iterator[tuple[Page, int]]:
    """Serve ``serve_dir`` on loopback and attach to a fresh headless chromium."""
    http_port, cdp_port = free_port(), free_port()
    profile = tempfile.mkdtemp(prefix="kc-e2e-")
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "http.server",
            str(http_port),
            "-b",
            "127.0.0.1",
            "-d",
            str(serve_dir),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    browser = subprocess.Popen(
        [chromium(), "--headless=new", f"--remote-debugging-port={cdp_port}",
         "--remote-debugging-address=127.0.0.1", f"--user-data-dir={profile}",
         "--disable-extensions", "--no-first-run", "--no-default-browser-check",
         "--password-store=basic", "--mute-audio", "--hide-scrollbars",
         "--enable-unsafe-swiftshader", f"--window-size={size}", "about:blank"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )  # fmt: skip
    try:
        sess = wait_for(lambda: cdp.connect(cdp_port), "chromium CDP")
        sess.call("Page.enable")
        sess.call("Network.enable")
        sess.call("Page.addScriptToEvaluateOnNewDocument", source=STUB)
        yield Page(sess), http_port
        sess.close()
    finally:
        browser.terminate()
        server.terminate()
        browser.wait(10)
        server.wait(10)
        shutil.rmtree(profile, ignore_errors=True)
