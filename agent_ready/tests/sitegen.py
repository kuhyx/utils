"""Build good and bad site trees in a temp dir (no static fixture files).

Generated at test time on purpose: mirror files such as ``index.md`` would
otherwise trip the repo's markdown-naming gate.
"""

from __future__ import annotations

import json
from pathlib import Path

ORIGIN = "https://example.test"

_TEXT = (
    "Dice roller for tabletop games. Roll any combination of polyhedral dice, "
    "keep the highest, and read the full breakdown of every throw. This text "
    "is in the initial HTML so an agent that never runs JavaScript can read it."
)

_LD = json.dumps(
    {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": "Dice",
        "url": ORIGIN,
    }
)

CATALOG = {
    "specVersion": "1.0",
    "host": {"displayName": "kuhy", "identifier": "did:web:example.test"},
    "entries": [
        {
            "identifier": "urn:air:example.test:docs:llms",
            "displayName": "llms.txt",
            "type": "text/plain",
            "url": f"{ORIGIN}/llms.txt",
        }
    ],
}

LLMS = f"""# Dice
> A dice roller for tabletop games.

Plain prose is allowed between sections.

## Pages
- [Home]({ORIGIN}/): what the roller does
- [About]({ORIGIN}/about/): who made it
"""

ROBOTS = f"""# robots.txt
User-agent: *
Disallow: /search/

Sitemap: {ORIGIN}/sitemap.xml
"""

SITEMAP = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{ORIGIN}/</loc></url>
  <url><loc>{ORIGIN}/about/</loc></url>
</urlset>
"""


def page(title: str, mirror: str, *, home: bool = False) -> str:
    """Return a server-rendered HTML page with every read-stage feature."""
    head = [
        f"<title>{title}</title>",
        f'<link rel="alternate" type="text/markdown" href="{mirror}">',
    ]
    if home:
        head += [
            '<link rel="ai-catalog" href="/.well-known/ai-catalog.json" type="application/ai-catalog+json">',
            '<link rel="alternate" type="text/plain" href="/llms.txt">',
            f'<script type="application/ld+json">{_LD}</script>',
        ]
    return (
        '<!doctype html><html lang="en"><head>' + "".join(head) + "</head><body>"
        f"<h1>{title}</h1><p>{_TEXT}</p>"
        '<pre><code class="language-python">print("d20")</code></pre>'
        '<nav><a href="/">Home</a> <a href="/about/">About</a> <a href="/llms.txt">llms.txt</a></nav>'
        "</body></html>"
    )


def mirror(title: str) -> str:
    """Return a markdown mirror with a language-tagged fence."""
    return f"# {title}\n\n{_TEXT}\n\n```python\nprint('d20')\n```\n"


def write(root: Path, rel: str, text: str) -> None:
    """Write ``text`` to ``root/rel``, creating parent dirs."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_good(root: Path) -> Path:
    """Create a fully compliant build output under ``root``."""
    write(root, "index.html", page("Dice", "/index.md", home=True))
    write(root, "index.md", mirror("Dice"))
    write(root, "about/index.html", page("About", "/about/index.md"))
    write(root, "about/index.md", mirror("About"))
    write(
        root,
        "404.html",
        "<!doctype html><html><body><h1>Not found</h1><p>No page at this address.</p></body></html>",
    )
    write(root, "robots.txt", ROBOTS)
    write(root, "sitemap.xml", SITEMAP)
    write(root, "llms.txt", LLMS)
    write(root, ".well-known/ai-catalog.json", json.dumps(CATALOG))
    return root


SHELL = '<!doctype html><html><head><title>App</title></head><body><div id="root"></div><script src="/app.js"></script></body></html>'


def build_bad(root: Path) -> Path:
    """Create a build output that violates every find/read item."""
    write(root, "index.html", SHELL)
    write(root, "about/index.html", SHELL)
    write(
        root,
        "robots.txt",
        "User-agent: *\nDisallow:\n\nUser-agent: GPTBot\nDisallow: /\n",
    )
    write(root, "sitemap.xml", "<html>not xml")
    write(root, "llms.txt", "# Dice\n\n## Pages\n- [About](/about/)\n")
    write(
        root,
        ".well-known/ai-catalog.json",
        json.dumps({"entries": [{"identifier": "x"}]}),
    )
    return root


def add_pages(root: Path, count: int, *, broken_last: bool = False) -> None:
    """Add ``count`` more sitemap pages; the last one an empty shell if asked."""
    urls = []
    for i in range(count):
        title = f"Post {i}"
        html = (
            SHELL if broken_last and i == count - 1 else page(title, f"/p{i}/index.md")
        )
        write(root, f"p{i}/index.html", html)
        write(root, f"p{i}/index.md", mirror(title))
        urls.append(f"  <url><loc>{ORIGIN}/p{i}/</loc></url>\n")
    write(
        root, "sitemap.xml", SITEMAP.replace("</urlset>", "".join(urls) + "</urlset>")
    )
