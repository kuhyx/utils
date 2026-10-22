"""Read stage: AR-READ-01..09 and 11 (AR-READ-10 is retired in spec v2.0)."""

from __future__ import annotations

import secrets

from agent_ready import formats
from agent_ready.context import CATALOG, HOME, LLMS, TEXT_TYPES, Ctx, link_header_href
from agent_ready.htmlscan import scan
from agent_ready.report import summarize


def _pages(ctx: Ctx) -> list[str]:
    """Homepage plus sitemap pages, capped. An empty sitemap is a READ-01 FAIL."""
    if not ctx.sitemap_pages:
        ctx.report.fail(
            "AR-READ-01", "sitemap yielded no pages; only the homepage was checked"
        )
    every = list(dict.fromkeys([HOME, *ctx.sitemap_pages]))
    pages = ctx.cap(every)
    if len(pages) < len(every):
        ctx.report.skip(
            "AR-READ-01",
            f"checked {len(pages)} of {len(every)} pages (--max-pages); rest unchecked",
        )
    ctx.site.prefetch(pages)
    return pages


def _mirror_href(ctx: Ctx, path: str) -> str | None:
    """Markdown mirror advertised by <link rel=alternate type=text/markdown> or Link header."""
    resp, page = ctx.page(path)
    href = page.link_href("alternate", "text/markdown")
    if href is None and ctx.live:
        href = link_header_href(resp, "alternate", "text/markdown")
    return href


def check_pages(ctx: Ctx) -> None:
    """AR-READ-01 text in initial HTML, AR-READ-05 tagged code, AR-READ-09 mirrors."""
    pages = _pages(ctx)
    home, _ = ctx.home()
    no_text: list[str] = []
    untagged: list[str] = []
    blocks = 0
    for path in pages:
        resp, page = ctx.page(path)
        if resp.status != 200:
            no_text.append(f"{path} (HTTP {resp.status})")
            continue
        if ctx.type_problem(resp, ("text/html",), path):
            no_text.append(f"{path} ({resp.ctype or 'no content-type'})")
        elif path != HOME and resp.body == home.body:
            no_text.append(f"{path} (byte-identical to the homepage shell)")
        elif len(page.text) < ctx.min_text:
            no_text.append(f"{path} ({len(page.text)} chars of text < {ctx.min_text})")
        blocks += page.code_blocks
        if page.untagged_code:
            untagged.append(f"{path} ({page.untagged_code} untagged <pre><code>)")
    ctx.report.verdict(
        "AR-READ-01",
        ["answer not in initial HTML: " + summarize(no_text)] if no_text else [],
        f"{len(pages)} pages carry >= {ctx.min_text} chars of text without JS",
    )
    md_untagged = _check_mirrors(ctx, pages)
    untagged += md_untagged
    ctx.report.verdict(
        "AR-READ-05",
        ["code without a language tag: " + summarize(untagged)] if untagged else [],
        f"{blocks} HTML code blocks (plus mirror fences) all language-tagged",
    )


def _check_mirrors(ctx: Ctx, pages: list[str]) -> list[str]:
    """AR-READ-09 for every page; returns mirrors with untagged fences (READ-05)."""
    bad: list[str] = []
    untagged: list[str] = []
    targets: dict[str, str] = {}
    for path in pages:
        if ctx.site.get(path).status != 200:
            continue
        href = _mirror_href(ctx, path)
        target = ctx.site.to_path(href, path) if href else None
        if target is None:
            bad.append(f"{path} (no text/markdown alternate link)")
        else:
            targets[path] = target
    ctx.site.prefetch(list(targets.values()))
    for path, target in targets.items():
        resp = ctx.site.get(target)
        if resp.status != 200:
            bad.append(f"{target} (HTTP {resp.status})")
        elif (
            ctx.type_problem(resp, TEXT_TYPES, target)
            or formats.looks_like_html(resp.text)
            or not resp.text.strip()
        ):
            bad.append(f"{target} (not markdown: {resp.ctype or 'empty'})")
        elif n := formats.untagged_fences(resp.text):
            untagged.append(f"{target} ({n} untagged fences)")
    ctx.report.verdict(
        "AR-READ-09",
        ["markdown mirror missing/broken: " + summarize(bad)] if bad else [],
        f"{len(targets)} pages advertise a working markdown mirror",
    )
    return untagged


def check_status_codes(ctx: Ctx) -> None:
    """AR-READ-02: unknown paths are a real 404 (url) / a 404.html exists (dist)."""
    if not ctx.live:
        resp = ctx.site.get(f"/agentready-probe-{secrets.token_hex(6)}")
        text = scan(resp.text).text if resp.body else ""
        ok = resp.status == 404 and len(text) >= 10
        ctx.report.verdict(
            "AR-READ-02",
            [] if ok else ["no 404.html with real text in the build output"],
            "404.html exists for unknown paths",
        )
        return
    token = secrets.token_hex(6)
    probes = [f"/agentready-probe-{token}", f"/agentready-probe-{token}/page.html"]
    ctx.site.prefetch(probes)
    bad = [
        f"{p} -> HTTP {s}"
        for p in probes
        if (s := ctx.site.get(p).status) not in (404, 410)
    ]
    ctx.report.verdict(
        "AR-READ-02",
        ["soft 404, unknown paths must return 404: " + ", ".join(bad)] if bad else [],
        "unknown paths return 404",
    )


def check_homepage(ctx: Ctx) -> None:
    """AR-READ-03 real links on the homepage, AR-READ-08 JSON-LD on it."""
    resp, page = ctx.home()
    links = {
        p
        for a in page.anchors
        if not a.startswith(("#", "javascript:", "mailto:"))
        and (p := ctx.site.to_path(a))
        and p != HOME
    }
    ok = resp.status == 200 and bool(links)
    ctx.report.verdict(
        "AR-READ-03",
        [] if ok else ["homepage HTML has no <a href> links to other pages"],
        f"homepage links {len(links)} pages in raw HTML",
    )
    problems = []
    if not page.jsonld_ok:
        problems.append(
            'homepage has no <script type="application/ld+json"> with @context'
        )
    if page.jsonld_bad:
        problems.append(
            f"{page.jsonld_bad} JSON-LD blocks fail to parse or lack @context"
        )
    ctx.report.verdict(
        "AR-READ-08", problems, f"homepage carries {page.jsonld_ok} JSON-LD blocks"
    )


def check_discovery_links(ctx: Ctx) -> None:
    """AR-READ-06: discovery files are linked from the homepage."""
    _, page = ctx.home()
    linked = {
        ctx.site.to_path(h)
        for h in [*page.anchors, *(href for _, _, href in page.links)]
    }
    files = [LLMS, CATALOG] + (["/openapi.json"] if ctx.act else [])
    for path in files:
        problems = []
        if not ctx.exists(path):
            problems.append(f"{path} does not exist")
        if path not in linked:
            problems.append(f"{path} is not linked from the homepage (<link> or <a>)")
        ctx.report.verdict(
            "AR-READ-06", problems, f"{path} exists and is linked from the homepage"
        )


def check_llms(ctx: Ctx) -> None:
    """AR-READ-07: llms.txt in the spec shape, every on-site link resolving."""
    resp = ctx.site.get(LLMS)
    if resp.status != 200:
        ctx.report.fail("AR-READ-07", f"{LLMS}: HTTP {resp.status}")
        return
    problems = ctx.type_problem(resp, TEXT_TYPES, LLMS) + formats.llms_problems(
        resp.text
    )
    if not formats.looks_like_html(resp.text):
        paths = [
            p for u in formats.llms_links(resp.text) if (p := ctx.site.to_path(u, LLMS))
        ]
        paths = ctx.cap(paths)
        ctx.site.prefetch(paths)
        broken = [p for p in paths if ctx.site.get(p).status != 200]
        if broken:
            problems.append("broken links: " + summarize(broken))
    ctx.report.verdict("AR-READ-07", problems, f"{LLMS} has H1, summary and link lists")


def skip_manual(ctx: Ctx) -> None:
    """Items with no mechanical check (reported, never silently dropped)."""
    ctx.report.skip(
        "AR-FIND-02", "first-party docs page answering user questions: manual review"
    )
    ctx.report.skip("AR-READ-04", "docs pages answer users' tasks: manual review")
    ctx.report.skip("AR-READ-11", "pricing page: n/a for sites without paid plans")
