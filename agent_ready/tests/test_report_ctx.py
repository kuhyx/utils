"""Report policy, Link-header parsing and context helpers."""

from __future__ import annotations

import io

from agent_ready.backends import Response
from agent_ready.context import link_header_href
from agent_ready.report import Report, Undeterminable, summarize
from agent_ready.tests.fakes import FakeSite, make_ctx, resp


def _boom() -> None:
    raise Undeterminable("refused")


def test_guard_turns_network_failure_into_skip_and_exit_3() -> None:
    out = io.StringIO()
    report = Report(out=out)
    report.guard("AR-FIND-01", _boom)
    assert out.getvalue() == "SKIP AR-FIND-01 undeterminable (network): refused\n"
    assert report.exit_code() == 3
    report.fail("AR-FIND-01", "x")
    assert report.exit_code() == 1


def test_summarize_notes_the_overflow() -> None:
    assert summarize(["a", "b"]) == "a, b"
    assert summarize(list("abcdef")) == "a, b, c, d (+2 more)"


def _linked(link: str) -> Response:
    return Response(200, "text/html", b"", {"link": link})


def test_link_header_skips_unusable_values() -> None:
    header = (
        "garbage, </no-rel>; type=x, </other>; rel=preload, "
        '</a.md>; rel="alternate"; type="text/plain", '
        '</b.md>; rel="alternate"; type="text/markdown"'
    )
    assert link_header_href(_linked(header), "alternate", "text/markdown") == "/b.md"
    assert link_header_href(_linked(header), "alternate") == "/a.md"
    assert link_header_href(_linked(header), "ai-catalog") is None
    assert link_header_href(_linked(""), "alternate") is None


def test_exists_rejects_html_fallback_for_files() -> None:
    ctx, _ = make_ctx(
        FakeSite({"/f.txt": resp("<html><head></head>"), "/p/": resp("<html>")})
    )
    assert not ctx.exists("/f.txt")
    assert ctx.exists("/p/")
    assert not ctx.exists("/missing.txt")
