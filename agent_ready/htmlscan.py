"""One-pass HTML scan: visible body text, links, JSON-LD and code blocks."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

_HIDDEN = {"script", "style", "noscript", "template", "svg", "head", "title"}
_LANG = re.compile(r"\b(language|lang)-\S+")


@dataclass
class PageScan:
    """What an agent that does not run JavaScript sees in a page."""

    text: str = ""
    links: list[tuple[set[str], str, str]] = field(default_factory=list)
    anchors: list[str] = field(default_factory=list)
    scripts: list[str] = field(default_factory=list)
    jsonld_ok: int = 0
    jsonld_bad: int = 0
    code_blocks: int = 0
    untagged_code: int = 0

    def link_href(self, rel: str, mime: str | None = None) -> str | None:
        """First ``<link>`` href with ``rel`` (and ``type`` if given)."""
        for rels, typ, href in self.links:
            if rel in rels and (mime is None or typ == mime):
                return href
        return None


def _tagged(attrs: dict[str, str]) -> bool:
    """True when an element carries a code-language marker."""
    return bool(_LANG.search(attrs.get("class", ""))) or bool(
        attrs.get("data-language") or attrs.get("data-lang")
    )


class _Scanner(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out = PageScan()
        self._hidden: list[str] = []
        self._text: list[str] = []
        self._pre: list[list[bool]] = []  # [pre_tagged, code_seen]
        self._ld: list[str] | None = None

    def handle_starttag(
        self, tag: str, attr_list: list[tuple[str, str | None]]
    ) -> None:
        attrs = {k: v or "" for k, v in attr_list}
        if tag == "body":  # </head> is optional in HTML; <body> always ends it
            self._hidden = [h for h in self._hidden if h not in ("head", "title")]
        if tag == "link" and attrs.get("href"):
            rels = set(attrs.get("rel", "").lower().split())
            self.out.links.append((rels, attrs.get("type", "").lower(), attrs["href"]))
        elif tag == "a" and attrs.get("href"):
            self.out.anchors.append(attrs["href"])
        elif tag == "script":
            if attrs.get("src"):
                self.out.scripts.append(attrs["src"])
            if attrs.get("type", "").lower() == "application/ld+json":
                self._ld = []
        elif tag == "pre":
            self._pre.append([_tagged(attrs), False])
        elif tag == "code" and self._pre and not self._pre[-1][1]:
            self._pre[-1][1] = True
            self.out.code_blocks += 1
            self.out.untagged_code += not (self._pre[-1][0] or _tagged(attrs))
        if tag in _HIDDEN:
            self._hidden.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._ld is not None:
            self._finish_ld("".join(self._ld))
            self._ld = None
        if tag == "pre" and self._pre:
            self._pre.pop()
        if tag in _HIDDEN and tag in self._hidden:
            while self._hidden and self._hidden.pop() != tag:
                pass

    def handle_data(self, data: str) -> None:
        if self._ld is not None:
            self._ld.append(data)
        elif not self._hidden:
            self._text.append(data)

    def _finish_ld(self, raw: str) -> None:
        try:
            doc = json.loads(raw)
        except ValueError:
            self.out.jsonld_bad += 1
            return
        nodes = doc if isinstance(doc, list) else [doc]
        ok = (
            all(
                isinstance(n, dict) and ("@context" in n or "@graph" in n)
                for n in nodes
            )
            and nodes
        )
        if ok:
            self.out.jsonld_ok += 1
        else:
            self.out.jsonld_bad += 1

    def result(self) -> PageScan:
        self.out.text = re.sub(r"\s+", " ", " ".join(self._text)).strip()
        return self.out


def scan(html: str) -> PageScan:
    """Scan an HTML document."""
    parser = _Scanner()
    parser.feed(html)
    parser.close()
    return parser.result()
