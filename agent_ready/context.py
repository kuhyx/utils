"""Shared state for one checker run (site, report, options, discoveries)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from agent_ready.backends import Response, Site
from agent_ready.formats import looks_like_html
from agent_ready.htmlscan import PageScan, scan
from agent_ready.report import Report

HOME = "/"
LLMS = "/llms.txt"
CATALOG = "/.well-known/ai-catalog.json"
TEXT_TYPES = ("text/plain", "text/markdown")


@dataclass
class Ctx:
    """Everything a check needs; filled in as checks discover the site."""

    site: Site
    report: Report
    min_text: int = 100
    max_pages: int = 40
    act: bool = False
    robots_text: str | None = None
    sitemap_pages: list[str] = field(default_factory=list)
    _scans: dict[str, PageScan] = field(default_factory=dict)

    @property
    def live(self) -> bool:
        """True in url mode (headers and content types are real)."""
        return self.site.live

    def cap(self, items: list[str]) -> list[str]:
        """Apply --max-pages in url mode only; dist mode is free, so check everything."""
        return items[: self.max_pages] if self.live else items

    def page(self, path: str) -> tuple[Response, PageScan]:
        """Fetch and scan an HTML page (scan memoized)."""
        resp = self.site.get(path)
        if path not in self._scans:
            self._scans[path] = scan(resp.text) if resp.status == 200 else PageScan()
        return resp, self._scans[path]

    def home(self) -> tuple[Response, PageScan]:
        """The homepage and its scan."""
        return self.page(HOME)

    def type_problem(
        self, resp: Response, allowed: tuple[str, ...], what: str
    ) -> list[str]:
        """Content-type problem for live responses (dist mode has none)."""
        if (
            not self.live
            or resp.ctype in allowed
            or any(a.endswith("+xml") and resp.ctype.endswith("+xml") for a in allowed)
        ):
            return []
        return [
            f"{what} served as {resp.ctype or 'no content-type'}, want {' or '.join(allowed)}"
        ]

    def exists(self, path: str) -> bool:
        """True when ``path`` is 200 and, for a non-page file, not an HTML fallback."""
        resp = self.site.get(path)
        is_page = path.endswith(("/", ".html"))
        return resp.status == 200 and (is_page or not looks_like_html(resp.text))


def link_header_href(resp: Response, rel: str, mime: str | None = None) -> str | None:
    """href of the first RFC 8288 ``Link`` header value with ``rel`` (and type)."""
    for part in re.split(r",\s*(?=<)", resp.headers.get("link", "")):
        match = re.match(r"\s*<([^>]*)>(.*)", part)
        if not match:
            continue
        params = match.group(2).lower()
        rels = re.search(r'rel="?([^";]+)"?', params)
        if not rels or rel not in rels.group(1).split():
            continue
        if mime is None or re.search(rf'type="?{re.escape(mime)}"?', params):
            return match.group(1)
    return None
