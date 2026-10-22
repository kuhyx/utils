"""Find stage: AR-FIND-01..04 (robots.txt, agent access, sitemap, AI Catalog)."""

from __future__ import annotations

import json
from urllib.parse import urlsplit

from agent_ready import formats
from agent_ready.context import CATALOG, HOME, LLMS, Ctx, link_header_href
from agent_ready.report import summarize

# Training, search-index and user-initiated fetchers named in the spec's
# crawl-policy notes. Real UA strings for the two training crawlers.
AGENT_UAS = {
    "ClaudeBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; ClaudeBot/1.0; +claudebot@anthropic.com)",
    "GPTBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.1; +https://openai.com/gptbot)",
    "Claude-SearchBot": "Claude-SearchBot/1.0",
    "OAI-SearchBot": "OAI-SearchBot/1.0; +https://openai.com/searchbot",
    "Claude-User": "Claude-User/1.0",
    "ChatGPT-User": "ChatGPT-User/1.0; +https://openai.com/bot",
}
_CHALLENGE = (
    "just a moment",
    "cf-chl",
    "challenge-platform",
    "attention required",
    "captcha",
)
XML_TYPES = ("application/xml", "text/xml", "application/rss+xml")


def check_robots(ctx: Ctx) -> None:
    """AR-FIND-01: robots.txt exists, is plain text and blocks no agent."""
    resp = ctx.site.get("/robots.txt")
    if resp.status != 200:
        ctx.report.fail("AR-FIND-01", f"/robots.txt: HTTP {resp.status}")
        return
    problems = ctx.type_problem(resp, ("text/plain",), "/robots.txt")
    if formats.looks_like_html(resp.text):
        ctx.report.fail(
            "AR-FIND-01",
            "; ".join([*problems, "/robots.txt body is an HTML page (SPA fallback?)"]),
        )
        return
    ctx.robots_text = resp.text
    groups = formats.parse_robots(resp.text)
    if not formats.has_wildcard_group(groups):
        problems.append("no 'User-agent: *' group (spec: one rule for all agents)")
    blocked = formats.blocked_agents(groups)
    if blocked:
        problems.append(f"blanket Disallow for: {', '.join(blocked)}")
    ctx.report.verdict(
        "AR-FIND-01",
        problems,
        "robots.txt is plain text, has a * group and blocks no agent",
    )


def check_agent_access(ctx: Ctx) -> None:
    """AR-FIND-01 (bot protection): homepage is 200 for each agent UA (url mode)."""
    if not ctx.live:
        ctx.report.skip("AR-FIND-01", "agent user-agent fetches need url mode")
        return
    base, _ = ctx.home()
    ctx.site.prefetch([HOME], tuple(AGENT_UAS.values()))
    bad = []
    for name, ua in AGENT_UAS.items():
        resp = ctx.site.get(HOME, ua)
        lowered = resp.text[:20000].lower()
        if resp.status != 200:
            bad.append(f"{name} HTTP {resp.status}")
        elif resp.body != base.body and any(m in lowered for m in _CHALLENGE):
            bad.append(f"{name} got a challenge page")
    ctx.report.verdict("AR-FIND-01", bad, f"homepage 200 for {', '.join(AGENT_UAS)}")


def _sitemap_paths(ctx: Ctx) -> list[str]:
    """Sitemap locations from robots.txt (also fixes the dist-mode origin)."""
    urls = formats.robots_sitemaps(ctx.robots_text or "")
    if urls and not ctx.live:
        parts = urlsplit(urls[0])
        ctx.site.origin = f"{parts.scheme}://{parts.netloc}"
    paths = [p for u in urls if (p := ctx.site.to_path(u))]
    if ctx.robots_text is None:
        ctx.report.fail("AR-FIND-03", "no valid robots.txt to reference the sitemap")
    elif not urls:
        ctx.report.fail("AR-FIND-03", "robots.txt has no 'Sitemap:' line")
    elif not paths:
        ctx.report.fail(
            "AR-FIND-03", f"robots.txt Sitemap is on another host: {urls[0]}"
        )
    else:
        ctx.report.ok("AR-FIND-03", f"robots.txt references {summarize(urls)}")
    return paths or ["/sitemap.xml"]


def _read_sitemap(ctx: Ctx, path: str, problems: list[str]) -> tuple[str, list[str]]:
    """Fetch and parse one sitemap; record problems; return (kind, locs)."""
    resp = ctx.site.get(path)
    if resp.status != 200:
        problems.append(f"{path}: HTTP {resp.status}")
        return "", []
    problems.extend(ctx.type_problem(resp, XML_TYPES, path))
    try:
        return formats.parse_sitemap(resp.body)
    except ValueError as exc:
        problems.append(f"{path}: {exc}")
        return "", []


def check_sitemap(ctx: Ctx) -> None:
    """AR-FIND-03: sitemap referenced from robots.txt, valid XML, on-site <loc>s."""
    problems: list[str] = []
    locs: list[str] = []
    for path in _sitemap_paths(ctx)[:5]:
        kind, found = _read_sitemap(ctx, path, problems)
        if kind == "sitemapindex":
            for child in [p for u in found[:10] if (p := ctx.site.to_path(u))]:
                locs += _read_sitemap(ctx, child, problems)[1]
        else:
            locs += found
    if locs and not ctx.live and ctx.site.origin.endswith("dist.invalid"):
        parts = urlsplit(locs[0])
        ctx.site.origin = f"{parts.scheme}://{parts.netloc}"
    pages = [p for loc in locs if (p := ctx.site.to_path(loc))]
    if len(pages) < len(locs):
        problems.append(
            f"{len(locs) - len(pages)} <loc> URLs are not on {ctx.site.origin}"
        )
    if not locs and not problems:
        problems.append("sitemap has no <loc> entries")
    ctx.sitemap_pages = list(dict.fromkeys(pages))
    ctx.report.verdict(
        "AR-FIND-03", problems, f"sitemap lists {len(ctx.sitemap_pages)} pages"
    )


def check_catalog(ctx: Ctx) -> None:
    """AR-FIND-04: valid AI Catalog, lists llms.txt, linked from homepage head."""
    resp = ctx.site.get(CATALOG)
    problems: list[str] = []
    if resp.status != 200:
        problems.append(f"{CATALOG}: HTTP {resp.status}")
    else:
        problems += ctx.type_problem(
            resp, ("application/ai-catalog+json", "application/json"), CATALOG
        )
        try:
            doc = json.loads(resp.body)
        except ValueError:
            doc = None
            problems.append(f"{CATALOG} is not JSON")
        if doc is not None:
            problems += formats.catalog_problems(doc)
            listed = {ctx.site.to_path(u) for u in formats.catalog_urls(doc)}
            if ctx.exists(LLMS) and LLMS not in listed:
                problems.append("catalog has no entry for /llms.txt")
    ctx.report.verdict("AR-FIND-04", problems, f"{CATALOG} is a valid AI Catalog")
    home, scan = ctx.home()
    href = scan.link_href("ai-catalog")
    ok = href is not None and ctx.site.to_path(href) == CATALOG
    ctx.report.verdict(
        "AR-FIND-04",
        []
        if ok
        else [
            'homepage head lacks <link rel="ai-catalog" href="/.well-known/ai-catalog.json">'
        ],
        "homepage head links the catalog",
    )
    if not ctx.live:
        ctx.report.skip(
            "AR-FIND-04", "HTTP Link header can only be checked in url mode"
        )
        return
    header = link_header_href(home, "ai-catalog")
    ok = header is not None and ctx.site.to_path(header) == CATALOG
    ctx.report.verdict(
        "AR-FIND-04",
        []
        if ok
        else [
            'homepage response lacks HTTP header Link: <...ai-catalog.json>; rel="ai-catalog"'
        ],
        "homepage sends the ai-catalog Link header",
    )
