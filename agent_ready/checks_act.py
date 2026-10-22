"""Act stage: AR-ACT-01..10. Opt-in (``--act``): only for sites with user actions."""

from __future__ import annotations

import json

from agent_ready import formats
from agent_ready.backends import HttpSite
from agent_ready.context import CATALOG, Ctx

_INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "agentready-check", "version": "1"},
    },
}


def _json(ctx: Ctx, path: str) -> object | None:
    """Parsed JSON at ``path`` when it is 200 and parses, else None."""
    resp = ctx.site.get(path)
    if resp.status != 200:
        return None
    try:
        return json.loads(resp.body)
    except ValueError:
        return None


def check_auth(ctx: Ctx) -> None:
    """AR-ACT-01: OAuth metadata (RFC 9728 ``resource`` or RFC 8414 ``issuer``)."""
    prm = _json(ctx, "/.well-known/oauth-protected-resource")
    asm = _json(ctx, "/.well-known/oauth-authorization-server")
    ok = (isinstance(prm, dict) and "resource" in prm) or (
        isinstance(asm, dict) and "issuer" in asm
    )
    ctx.report.verdict(
        "AR-ACT-01",
        []
        if ok
        else [
            "no OAuth metadata under /.well-known (oauth-protected-resource / oauth-authorization-server)"
        ],
        "OAuth metadata discoverable under /.well-known",
    )


def check_openapi(ctx: Ctx) -> None:
    """AR-ACT-02: /openapi.json with paths and an operationId on every operation."""
    doc = _json(ctx, "/openapi.json")
    if not isinstance(doc, dict) or not isinstance(doc.get("openapi"), str):
        ctx.report.fail("AR-ACT-02", "/openapi.json missing or not an OpenAPI document")
        return
    paths = doc.get("paths") if isinstance(doc.get("paths"), dict) else {}
    ops = [
        op
        for item in paths.values()
        if isinstance(item, dict)
        for m, op in item.items()
        if m in ("get", "post", "put", "patch", "delete")
    ]
    missing = sum(
        1 for op in ops if not (isinstance(op, dict) and op.get("operationId"))
    )
    problems = ["no operations in paths"] if not ops else []
    if missing:
        problems.append(f"{missing} operations lack operationId")
    ctx.report.verdict(
        "AR-ACT-02", problems, f"/openapi.json describes {len(ops)} operations"
    )


def _mcp_ok(ctx: Ctx) -> bool | None:
    """True if /mcp answers initialize (or is OAuth-gated); None in dist mode."""
    if not isinstance(ctx.site, HttpSite):
        return None
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    resp = ctx.site.request("/mcp", data=json.dumps(_INIT).encode(), headers=headers)
    if resp.status == 401:
        return "www-authenticate" in resp.headers
    return resp.status == 200 and '"jsonrpc"' in resp.text and '"result"' in resp.text


def check_mcp(ctx: Ctx) -> None:
    """AR-ACT-03 MCP at /mcp, AR-ACT-04 server card, AR-ACT-10 an interface exists."""
    ok = _mcp_ok(ctx)
    if ok is None:
        ctx.report.skip("AR-ACT-03", "/mcp is a server endpoint: check in url mode")
        ctx.report.skip("AR-ACT-10", "MCP/CLI interface: check in url mode")
    else:
        ctx.report.verdict(
            "AR-ACT-03",
            []
            if ok
            else [
                "/mcp does not answer an MCP initialize (nor 401 + WWW-Authenticate)"
            ],
            "/mcp answers MCP initialize",
        )
        ctx.report.verdict(
            "AR-ACT-10",
            []
            if ok
            else ["no MCP server at /mcp; a CLI (AR-ACT-06) cannot be auto-detected"],
            "agents can act through /mcp",
        )
    cards = [
        t
        for t in formats.catalog_types(_json(ctx, CATALOG))
        if t == "application/mcp-server-card+json"
    ]
    ctx.report.verdict(
        "AR-ACT-04",
        [] if cards else ["AI Catalog lists no application/mcp-server-card+json entry"],
        "AI Catalog lists an MCP server card",
    )


def check_webmcp(ctx: Ctx) -> None:
    """AR-ACT-07: WebMCP tools registered on document.modelContext."""
    resp, page = ctx.home()
    sources = [resp.text]
    for src in page.scripts[:10]:
        path = ctx.site.to_path(src)
        if path:
            sources.append(ctx.site.get(path).text)
    found = any("modelContext" in s for s in sources)
    ctx.report.verdict(
        "AR-ACT-07",
        [] if found else ["no document.modelContext usage in homepage HTML/scripts"],
        "homepage registers WebMCP tools",
    )


def run_act(ctx: Ctx) -> None:
    """All act checks, or one SKIP line when the stage is off."""
    if not ctx.act:
        ctx.report.skip(
            "AR-ACT-10", "act stage off (pass --act for sites with user actions)"
        )
        return
    ctx.report.guard("AR-ACT-01", lambda: check_auth(ctx))
    ctx.report.guard("AR-ACT-02", lambda: check_openapi(ctx))
    ctx.report.guard("AR-ACT-03", lambda: check_mcp(ctx))
    ctx.report.guard("AR-ACT-07", lambda: check_webmcp(ctx))
    ctx.report.skip("AR-ACT-05", "MCP Apps ui:// view: manual review")
    ctx.report.skip("AR-ACT-06", "SDKs on npm/PyPI and a CLI: manual review")
    ctx.report.skip("AR-ACT-08", "agent payments: n/a unless the product charges")
    ctx.report.skip("AR-ACT-09", "NLWeb /ask endpoint: manual review")
