"""Unit tests for the format validators and the HTML scanner."""

from __future__ import annotations

import pytest

from agent_ready import formats, htmlscan
from agent_ready.tests import sitegen

# Verbatim from spec/spec.md "llms.txt shape (informative)".
SPEC_LLMS = """# Acme
> Acme ships a payments API for developers.

## Docs
- [Quickstart](https://example.com/docs/quickstart): first charge in one request
- [Authentication](https://example.com/docs/auth): API keys, scopes, rotation

## API
- [OpenAPI](https://example.com/openapi.json): full request and response contract
"""

# Shape of https://vercel.com/.well-known/ai-catalog.json (2026-10-22), trimmed.
VERCEL_CATALOG = {
    "specVersion": "1.0",
    "host": {"displayName": "Vercel", "identifier": "https://vercel.com"},
    "entries": [
        {
            "identifier": "urn:air:vercel.com:api:rest",
            "displayName": "Vercel REST API",
            "type": "application/json",
            "url": "https://vercel.com/openapi.json",
            "tags": ["api"],
        }
    ],
}


def test_llms_spec_example_is_valid() -> None:
    assert formats.llms_problems(SPEC_LLMS) == []


def test_llms_allows_prose_and_plain_bullets() -> None:
    text = SPEC_LLMS.replace(
        "## API", "Version: v2.0\n\n## Notes\n- plain bullet\n\n## API"
    )
    assert formats.llms_problems(text) == []


@pytest.mark.parametrize(
    ("mutate", "needle"),
    [
        (lambda t: t.replace("# Acme\n", ""), "H1"),
        (
            lambda t: t.replace("> Acme ships a payments API for developers.\n", ""),
            "blockquote",
        ),
        (lambda t: "# Acme\n> summary\n\nno sections\n", "link list"),
        (lambda t: "<!doctype html><html></html>", "HTML"),
    ],
)
def test_llms_rejects(mutate: object, needle: str) -> None:
    problems = formats.llms_problems(mutate(SPEC_LLMS))  # type: ignore[operator]
    assert any(needle in p for p in problems), problems


def test_llms_links() -> None:
    assert formats.llms_links(SPEC_LLMS)[0] == "https://example.com/docs/quickstart"


def test_catalog_valid_examples() -> None:
    assert formats.catalog_problems(VERCEL_CATALOG) == []
    assert formats.catalog_problems(sitegen.CATALOG) == []
    minimal = {
        "specVersion": "1.0",
        "entries": [{"identifier": "a", "type": "t", "data": {}}],
    }
    assert formats.catalog_problems(minimal) == []


@pytest.mark.parametrize(
    ("doc", "needle"),
    [
        ([], "object"),
        ({"entries": []}, "specVersion"),
        ({"specVersion": "1", "entries": []}, "Major.Minor"),
        ({"specVersion": "1.0"}, "entries"),
        ({"specVersion": "1.0", "entries": [{"type": "t", "url": "u"}]}, "identifier"),
        ({"specVersion": "1.0", "entries": [{"identifier": "i", "url": "u"}]}, "type"),
        (
            {
                "specVersion": "1.0",
                "entries": [{"identifier": "i", "type": "t", "url": "u", "data": 1}],
            },
            "exactly one",
        ),
        ({"specVersion": "1.0", "entries": [], "host": {}}, "host.displayName"),
    ],
)
def test_catalog_rejects(doc: object, needle: str) -> None:
    assert any(needle in p for p in formats.catalog_problems(doc)), (
        formats.catalog_problems(doc)
    )


def test_robots_blanket_blocks() -> None:
    text = "User-agent: *\nDisallow:\n\nUser-Agent: GPTBot\nUser-agent: CCBot\nDisallow: /*\n"
    groups = formats.parse_robots(text)
    assert formats.has_wildcard_group(groups)
    assert formats.blocked_agents(groups) == ["gptbot", "ccbot"]


def test_robots_partial_disallow_and_allow_override() -> None:
    text = "User-agent: *\nDisallow: /search/\n\nUser-agent: ClaudeBot\nDisallow: /\nAllow: /\n"
    assert formats.blocked_agents(formats.parse_robots(text)) == []
    assert formats.robots_sitemaps("Sitemap: https://x.test/s.xml\n") == [
        "https://x.test/s.xml"
    ]


def test_sitemap_parse() -> None:
    kind, locs = formats.parse_sitemap(sitegen.SITEMAP.encode())
    assert kind == "urlset"
    assert locs == ["https://example.test/", "https://example.test/about/"]
    with pytest.raises(ValueError):
        formats.parse_sitemap(b"<html>not xml")


def test_untagged_fences() -> None:
    assert formats.untagged_fences("```python\nx\n```\n") == 0
    assert formats.untagged_fences("```\nx\n```\n~~~\ny\n~~~\n") == 2


def test_htmlscan_good_home() -> None:
    scan = htmlscan.scan(sitegen.page("Dice", "/index.md", home=True))
    assert len(scan.text) > 150
    assert scan.code_blocks == 1 and scan.untagged_code == 0
    assert scan.link_href("alternate", "text/markdown") == "/index.md"
    assert scan.link_href("ai-catalog") == "/.well-known/ai-catalog.json"
    assert "/about/" in scan.anchors
    assert scan.jsonld_ok == 1


def test_htmlscan_shell_has_no_text() -> None:
    scan = htmlscan.scan(sitegen.SHELL)
    assert scan.text.strip() == ""  # <title> is head, not body text
    assert scan.anchors == []
    bare = htmlscan.scan(
        '<pre><code>x</code></pre><script type="application/ld+json">{bad</script>'
    )
    assert bare.untagged_code == 1 and bare.jsonld_bad == 1


def test_sitemap_wrong_root_is_rejected() -> None:
    with pytest.raises(ValueError, match="not <urlset>"):
        formats.parse_sitemap(b"<feed><loc>https://x.test/</loc></feed>")


def test_catalog_entry_must_be_an_object() -> None:
    doc = {"specVersion": "1.0", "entries": ["nope"]}
    assert formats.catalog_problems(doc) == ["entries[0]: must be an object"]


def test_catalog_accessors_tolerate_invalid_docs() -> None:
    for doc in ([], {"entries": "x"}):
        assert formats.catalog_urls(doc) == []
        assert formats.catalog_types(doc) == []
    assert formats.catalog_urls(sitegen.CATALOG) == [f"{sitegen.ORIGIN}/llms.txt"]


def test_fence_inside_fence_is_not_a_new_block() -> None:
    nested = "````md\n```\ninner\n```\n````\n"
    assert formats.untagged_fences(nested) == 0
    assert formats.untagged_fences("```python\n~~~\n```\n```\nz\n```\n") == 1


def test_htmlscan_jsonld_without_context_is_bad() -> None:
    scan = htmlscan.scan(
        '<script type="application/ld+json">{"name": "x"}</script>'
        '<script type="application/ld+json">[]</script>'
    )
    assert scan.jsonld_ok == 0 and scan.jsonld_bad == 2


def test_htmlscan_unclosed_inner_hidden_tag_closes_with_outer() -> None:
    scan = htmlscan.scan("<body><template><noscript>x</template><p>visible</p></body>")
    assert scan.text == "visible"
