"""Live-mode checks driven by canned responses (no sockets, no network)."""

from __future__ import annotations

import pytest

from agent_ready import checks_act, checks_find, checks_read
from agent_ready.backends import Response
from agent_ready.tests import sitegen
from agent_ready.tests.fakes import FakeHttp, make_ctx, resp

LONG = "Readable text for agents that never run JavaScript. " * 4
MD_LINK = '</index.md>; rel="alternate"; type="text/markdown"'


def _home(*, ctype: str = "text/html", **headers: str) -> Response:
    return resp(f"<html><body><p>{LONG}</p></body></html>", ctype, **headers)


def test_challenge_page_for_one_agent_is_reported() -> None:
    challenge = resp("<html>Just a moment...</html>")
    ua = checks_find.AGENT_UAS["GPTBot"]
    site = FakeHttp({"/": _home()}, ua_pages={("/", ua): challenge})
    ctx, out = make_ctx(site)
    checks_find.check_agent_access(ctx)
    assert out.getvalue().startswith("FAIL AR-FIND-01 GPTBot got a challenge page")


def test_sitemap_on_another_host_is_a_failure() -> None:
    robots = "User-agent: *\nDisallow:\nSitemap: https://other.test/sitemap.xml\n"
    site = FakeHttp({"/robots.txt": resp(robots, "text/plain")})
    ctx, out = make_ctx(site)
    checks_find.check_robots(ctx)
    ctx.sitemap_pages = []
    assert checks_find._sitemap_paths(ctx) == ["/sitemap.xml"]
    assert (
        "Sitemap is on another host: https://other.test/sitemap.xml" in out.getvalue()
    )


def test_markdown_mirror_advertised_only_by_link_header() -> None:
    site = FakeHttp(
        {
            "/": _home(link=MD_LINK),
            "/index.md": resp(sitegen.mirror("Home"), "text/markdown"),
        }
    )
    ctx, out = make_ctx(site)
    checks_read.check_pages(ctx)
    assert (
        "PASS AR-READ-09 1 pages advertise a working markdown mirror" in out.getvalue()
    )


def test_page_served_with_wrong_content_type() -> None:
    ctx, out = make_ctx(FakeHttp({"/": _home(ctype="text/plain")}))
    checks_read.check_pages(ctx)
    assert (
        "FAIL AR-READ-01 answer not in initial HTML: / (text/plain)" in out.getvalue()
    )


def _mcp(status: int, **headers: str) -> Response:
    return Response(status, "application/json", b"{}", dict(headers))


@pytest.mark.parametrize(
    ("answer", "status"),
    [
        (_mcp(401, **{"www-authenticate": "Bearer"}), "PASS"),
        (_mcp(401), "FAIL"),
    ],
)
def test_mcp_behind_oauth_needs_www_authenticate(answer: Response, status: str) -> None:
    ctx, out = make_ctx(FakeHttp({}, mcp=answer), act=True)
    checks_act.check_mcp(ctx)
    assert f"{status} AR-ACT-03" in out.getvalue()


def test_act_off_reports_a_single_skip() -> None:
    ctx, out = make_ctx(FakeHttp({}))
    checks_act.run_act(ctx)
    assert out.getvalue().startswith("SKIP AR-ACT-10 act stage off")
