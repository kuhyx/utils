"""Dist-mode scenarios: one mutation of the good tree per failing branch."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_ready.tests import sitegen
from agent_ready.tests.fakes import lines_for, run_main

OPENAPI_OP = {"get": {"operationId": "ping"}}


def test_robots_without_wildcard_group(
    capsys: pytest.CaptureFixture[str], good_dir: Path
) -> None:
    robots = f"User-agent: Foo\nDisallow: /x\n\nSitemap: {sitegen.ORIGIN}/sitemap.xml\n"
    sitegen.write(good_dir, "robots.txt", robots)
    _, lines = run_main(capsys, "dist", str(good_dir))
    assert "no 'User-agent: *' group" in lines_for(lines, "AR-FIND-01", "FAIL")[0]


def test_sitemap_found_without_robots_reference_sets_origin(
    capsys: pytest.CaptureFixture[str], good_dir: Path
) -> None:
    sitegen.write(good_dir, "robots.txt", "User-agent: *\nDisallow:\n")
    code, lines = run_main(capsys, "dist", str(good_dir))
    assert code == 1
    assert "no 'Sitemap:' line" in lines_for(lines, "AR-FIND-03", "FAIL")[0]
    assert lines_for(lines, "AR-FIND-03", "FAIL")[1:] == []
    assert lines_for(lines, "AR-READ-01", "PASS")


def test_sitemap_index_follows_children(
    capsys: pytest.CaptureFixture[str], good_dir: Path
) -> None:
    child = f"{sitegen.ORIGIN}/sitemap-pages.xml"
    index = (
        '<?xml version="1.0"?><sitemapindex '
        'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"<sitemap><loc>{child}</loc></sitemap></sitemapindex>"
    )
    sitegen.write(good_dir, "sitemap-pages.xml", sitegen.SITEMAP)
    sitegen.write(good_dir, "sitemap.xml", index)
    code, lines = run_main(capsys, "dist", str(good_dir))
    assert code == 0, lines
    assert "lists 2 pages" in lines_for(lines, "AR-FIND-03", "PASS")[-1]


def test_sitemap_with_offsite_locs_and_none_at_all(
    capsys: pytest.CaptureFixture[str], good_dir: Path
) -> None:
    urlset = '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{}</urlset>'
    off = urlset.format("<url><loc>https://other.test/x/</loc></url>")
    sitegen.write(good_dir, "sitemap.xml", off)
    _, lines = run_main(capsys, "dist", str(good_dir))
    assert "1 <loc> URLs are not on" in lines_for(lines, "AR-FIND-03", "FAIL")[0]
    sitegen.write(good_dir, "sitemap.xml", urlset.format(""))
    _, lines = run_main(capsys, "dist", str(good_dir))
    assert "no <loc> entries" in lines_for(lines, "AR-FIND-03", "FAIL")[0]
    assert "sitemap yielded no pages" in lines_for(lines, "AR-READ-01", "FAIL")[0]


def test_sitemap_pages_missing_or_copies_of_the_shell(
    capsys: pytest.CaptureFixture[str], good_dir: Path
) -> None:
    home = (good_dir / "index.html").read_text()
    sitegen.write(good_dir, "dup/index.html", home)
    extra = "".join(
        f"<url><loc>{sitegen.ORIGIN}/{p}/</loc></url>" for p in ("dup", "gone")
    )
    sitemap = (good_dir / "sitemap.xml").read_text()
    sitegen.write(
        good_dir, "sitemap.xml", sitemap.replace("</urlset>", extra + "</urlset>")
    )
    code, lines = run_main(capsys, "dist", str(good_dir))
    assert code == 1
    problem = lines_for(lines, "AR-READ-01", "FAIL")[0]
    assert "/gone/ (HTTP 404)" in problem
    assert "/dup/ (byte-identical to the homepage shell)" in problem


def test_markdown_mirror_with_untagged_fence(
    capsys: pytest.CaptureFixture[str], good_dir: Path
) -> None:
    sitegen.write(good_dir, "about/index.md", "# About\n\n```\nplain\n```\n")
    _, lines = run_main(capsys, "dist", str(good_dir))
    assert "about/index.md (1 untagged fences)" in lines_for(lines, "AR-READ-05")[0]


def test_llms_with_broken_link(
    capsys: pytest.CaptureFixture[str], good_dir: Path
) -> None:
    llms = (good_dir / "llms.txt").read_text() + "- [Gone](/gone/): missing\n"
    sitegen.write(good_dir, "llms.txt", llms)
    _, lines = run_main(capsys, "dist", str(good_dir))
    assert "broken links: /gone/" in lines_for(lines, "AR-READ-07", "FAIL")[0]


def test_homepage_with_unparseable_json_ld(
    capsys: pytest.CaptureFixture[str], good_dir: Path
) -> None:
    home = (good_dir / "index.html").read_text()
    sitegen.write(good_dir, "index.html", home.replace('"@context"', "@context"))
    _, lines = run_main(capsys, "dist", str(good_dir))
    assert "1 JSON-LD blocks fail" in lines_for(lines, "AR-READ-08", "FAIL")[-1]


def test_webmcp_found_in_linked_script(
    capsys: pytest.CaptureFixture[str], good_dir: Path
) -> None:
    home = (good_dir / "index.html").read_text()
    scripts = '<script src="https://cdn.other.test/x.js"></script><script src="/app.js"></script>'
    sitegen.write(good_dir, "index.html", home.replace("</body>", scripts + "</body>"))
    sitegen.write(good_dir, "app.js", "document.modelContext.registerTool({});")
    _, lines = run_main(capsys, "dist", str(good_dir), "--act")
    assert lines_for(lines, "AR-ACT-07", "PASS")


@pytest.mark.parametrize(
    ("doc", "status", "needle"),
    [
        ({"openapi": "3.1.0", "paths": {"/p": OPENAPI_OP}}, "PASS", "1 operations"),
        (
            {"openapi": "3.1.0", "paths": {"/p": {"get": {}}}},
            "FAIL",
            "lack operationId",
        ),
        ({"openapi": "3.1.0", "paths": {}}, "FAIL", "no operations in paths"),
        ({"openapi": "3.1.0", "paths": 5}, "FAIL", "no operations in paths"),
        (
            {
                "openapi": "3.1.0",
                "paths": {"/a": "x", "/b": {"parameters": [], "get": 1}},
            },
            "FAIL",
            "1 operations lack",
        ),
    ],
)
def test_openapi_document_shapes(
    capsys: pytest.CaptureFixture[str],
    good_dir: Path,
    doc: dict[str, object],
    status: str,
    needle: str,
) -> None:
    sitegen.write(good_dir, "openapi.json", json.dumps(doc))
    _, lines = run_main(capsys, "dist", str(good_dir), "--act")
    found = lines_for(lines, "AR-ACT-02", status)
    assert found and needle in found[0], lines_for(lines, "AR-ACT-02")
