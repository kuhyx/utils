"""Validators for the file formats AgentReady points at.

robots.txt (RFC 9309), sitemap.xml (sitemaps.org), llms.txt (agentready
spec "llms.txt shape" / llmstxt.org) and the AI Catalog
(github.com/Agent-Card/ai-catalog, specification/ai-catalog.md).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

_LINK_ITEM = re.compile(r"^\s*[-*]\s+\[[^\]]+\]\(([^)\s]+)\)")
_FENCE = re.compile(r"^\s{0,3}(```+|~~~+)\s*(\S*)")
_SPEC_VERSION = re.compile(r"^\d+\.\d+$")


def looks_like_html(text: str) -> bool:
    """True when a supposedly plain-text/XML/JSON body is an HTML page."""
    head = text.lstrip()[:200].lower()
    return head.startswith(("<!doctype html", "<html")) or "<head" in head


# --------------------------------------------------------------- robots.txt
@dataclass
class RobotsGroup:
    """One ``User-agent`` group and its rules, in file order."""

    agents: list[str] = field(default_factory=list)
    rules: list[tuple[str, str]] = field(default_factory=list)


def parse_robots(text: str) -> list[RobotsGroup]:
    """Parse robots.txt into groups (consecutive User-agent lines share one)."""
    groups: list[RobotsGroup] = []
    current: RobotsGroup | None = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if current is None or current.rules:
                current = RobotsGroup()
                groups.append(current)
            current.agents.append(value.lower())
        elif key in ("allow", "disallow") and current is not None:
            current.rules.append((key, value))
    return groups


def has_wildcard_group(groups: list[RobotsGroup]) -> bool:
    """True when a ``User-agent: *`` group exists (one rule for all agents)."""
    return any("*" in g.agents for g in groups)


def blocked_agents(groups: list[RobotsGroup]) -> list[str]:
    """Agents whose group disallows the whole site (``/`` or ``/*``).

    An empty ``Disallow:`` allows everything; an ``Allow: /`` in the same
    group wins over the blanket disallow (longest-match tie goes to allow).
    """
    blocked: list[str] = []
    for group in groups:
        disallow_all = any(k == "disallow" and v in ("/", "/*") for k, v in group.rules)
        allow_all = any(k == "allow" and v in ("/", "/*") for k, v in group.rules)
        if disallow_all and not allow_all:
            blocked.extend(group.agents)
    return blocked


def robots_sitemaps(text: str) -> list[str]:
    """Return every ``Sitemap:`` URL."""
    out = []
    for raw in text.splitlines():
        key, _, value = raw.partition(":")
        if key.strip().lower() == "sitemap" and value.strip():
            out.append(value.strip())
    return out


# -------------------------------------------------------------- sitemap.xml
def parse_sitemap(body: bytes) -> tuple[str, list[str]]:
    """Return (root kind ``urlset``/``sitemapindex``, list of <loc> values).

    Raises ValueError for anything that is not a sitemap document.
    """
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise ValueError(f"not XML: {exc}") from exc
    kind = root.tag.rsplit("}", 1)[-1]
    if kind not in ("urlset", "sitemapindex"):
        raise ValueError(f"root element <{kind}> is not <urlset>/<sitemapindex>")
    locs = [
        (el.text or "").strip()
        for el in root.iter()
        if el.tag.rsplit("}", 1)[-1] == "loc"
    ]
    return kind, [loc for loc in locs if loc]


# ----------------------------------------------------------------- llms.txt
def llms_problems(text: str) -> list[str]:
    """Check llms.txt shape: H1 first, blockquote summary, H2 link lists."""
    if looks_like_html(text):
        return ["body is an HTML page, not llms.txt markdown"]
    lines = [ln for ln in text.splitlines() if ln.strip()]
    problems = []
    if not lines or not re.match(r"^# \S", lines[0]):
        problems.append("first line must be an H1 title ('# Name')")
    if not any(ln.startswith(">") for ln in lines[:4]):
        problems.append("missing blockquote summary ('> ...') after the H1")
    in_h2 = False
    links = 0
    for ln in lines:
        if ln.startswith("## "):
            in_h2 = True
        elif in_h2 and _LINK_ITEM.match(ln):
            links += 1
    if links == 0:
        problems.append("no '## Section' with a '- [name](url): notes' link list")
    return problems


def llms_links(text: str) -> list[str]:
    """Return every link-list URL in llms.txt, in order."""
    return [m.group(1) for ln in text.splitlines() if (m := _LINK_ITEM.match(ln))]


# --------------------------------------------------------------- ai-catalog
def catalog_problems(doc: object) -> list[str]:
    """Validate an AI Catalog (Level 1 + Host Info if present)."""
    if not isinstance(doc, dict):
        return ["top level must be a JSON object"]
    problems = []
    version = doc.get("specVersion")
    if not isinstance(version, str):
        problems.append("missing string specVersion")
    elif not _SPEC_VERSION.match(version):
        problems.append(f"specVersion {version!r} is not 'Major.Minor'")
    host = doc.get("host")
    if host is not None and not (
        isinstance(host, dict) and isinstance(host.get("displayName"), str)
    ):
        problems.append("host.displayName (string) is required when host is present")
    entries = doc.get("entries")
    if not isinstance(entries, list):
        return [*problems, "missing entries array"]
    for i, entry in enumerate(entries):
        problems.extend(f"entries[{i}]: {p}" for p in _entry_problems(entry))
    return problems


def _entry_problems(entry: object) -> list[str]:
    """Problems with one Catalog Entry."""
    if not isinstance(entry, dict):
        return ["must be an object"]
    problems = [
        f"missing string {k}"
        for k in ("identifier", "type")
        if not isinstance(entry.get(k), str)
    ]
    if ("url" in entry) == ("data" in entry):
        problems.append("must carry exactly one of url/data")
    return problems


def catalog_urls(doc: object) -> list[str]:
    """Every entry ``url`` in a catalog (empty for invalid docs)."""
    if not isinstance(doc, dict) or not isinstance(doc.get("entries"), list):
        return []
    return [
        e["url"]
        for e in doc["entries"]
        if isinstance(e, dict) and isinstance(e.get("url"), str)
    ]


def catalog_types(doc: object) -> list[str]:
    """Every entry ``type`` in a catalog."""
    if not isinstance(doc, dict) or not isinstance(doc.get("entries"), list):
        return []
    return [
        e["type"]
        for e in doc["entries"]
        if isinstance(e, dict) and isinstance(e.get("type"), str)
    ]


# ----------------------------------------------------------------- markdown
def untagged_fences(text: str) -> int:
    """Count opening code fences with no language info string."""
    count = 0
    open_fence = ""
    for line in text.splitlines():
        match = _FENCE.match(line)
        if not match:
            continue
        marker, info = match.groups()
        if open_fence:
            if (
                marker[0] == open_fence[0]
                and len(marker) >= len(open_fence)
                and not info
            ):
                open_fence = ""
            continue
        open_fence = marker
        count += not info
    return count
