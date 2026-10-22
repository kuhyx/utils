"""In-memory sites and CLI helpers for tests that need exact responses."""

from __future__ import annotations

import io

import pytest

from agent_ready.backends import DEFAULT_UA, HttpSite, Response, Site
from agent_ready.check import main
from agent_ready.context import Ctx
from agent_ready.report import Report

HTML = "text/html"
_MISSING = Response(404, HTML, b"")


def resp(body: str, ctype: str = HTML, status: int = 200, **headers: str) -> Response:
    """Build a Response; ``headers`` keys are already lowercase names."""
    return Response(status, ctype, body.encode(), dict(headers))


class FakeSite(Site):
    """A dist-like (``live=False``) site answering from a dict."""

    def __init__(self, pages: dict[str, Response]) -> None:
        super().__init__("https://fake.test")
        self.pages = pages

    def _fetch(self, path: str, ua: str) -> Response:
        return self.pages.get(path, _MISSING)


class FakeHttp(HttpSite):
    """A live site with no sockets: per-path (and per-UA) canned responses."""

    def __init__(
        self,
        pages: dict[str, Response],
        ua_pages: dict[tuple[str, str], Response] | None = None,
        mcp: Response | None = None,
    ) -> None:
        super().__init__("https://fake.test")
        self.pages = pages
        self.ua_pages = ua_pages or {}
        self.mcp = mcp or _MISSING

    def _fetch(self, path: str, ua: str) -> Response:
        return self.ua_pages.get((path, ua)) or self.pages.get(path, _MISSING)

    def request(
        self,
        path: str,
        ua: str = DEFAULT_UA,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> Response:
        """The canned MCP answer, whatever the request."""
        return self.mcp


def make_ctx(site: Site, *, act: bool = False) -> tuple[Ctx, io.StringIO]:
    """A Ctx writing to a StringIO; returns it with that buffer."""
    out = io.StringIO()
    return Ctx(site=site, report=Report(out=out), act=act), out


def run_main(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, list[str]]:
    """Run the CLI in-process; return exit code and output lines."""
    code = main(list(argv))
    return code, capsys.readouterr().out.splitlines()


def lines_for(lines: list[str], ar_id: str, status: str = "") -> list[str]:
    """Output lines for ``ar_id`` (optionally only one status)."""
    return [
        ln
        for ln in lines
        if ln.split()[1] == ar_id and (not status or ln.startswith(status))
    ]
