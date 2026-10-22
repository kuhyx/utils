# AgentReady spec notes

These notes record what the checker implements and where each rule comes from.
Fetched 2026-10-22.

## Sources

- AgentReady v2.0 (October 2026, MIT):
  <https://github.com/agentready-org/standard/blob/main/spec/spec.md>,
  canonical site <https://agentready.org>.
- AI Catalog (the format behind `AR-FIND-04`):
  <https://github.com/Agent-Card/ai-catalog/blob/main/specification/ai-catalog.md>.
  AgentReady defines no catalog schema of its own ("AgentReady does not
  introduce its own bespoke manifest"), so the checker uses this one.
- llms.txt: the spec's informative "llms.txt shape" example, and <https://llmstxt.org/>.

## Requirements (quoted from spec.md)

| ID | Level | Requirement | Checker |
|---|---|---|---|
| AR-FIND-01 | MUST | "The site **MUST NOT** block agent and crawler access to public content, in `robots.txt` or at the network layer." | robots.txt is 200 `text/plain` and not HTML. It has a `User-agent: *` group, and no group has a blanket `Disallow: /`. In url mode the homepage returns 200 with no challenge page for ClaudeBot, GPTBot, Claude-SearchBot, OAI-SearchBot, Claude-User and ChatGPT-User. |
| AR-FIND-02 | SHOULD | "Answers agents are expected to cite **SHOULD** be published on one canonical, current, first-party docs page." | SKIP (manual) |
| AR-FIND-03 | SHOULD | "The site **SHOULD** list its pages in a `sitemap.xml` referenced from `robots.txt`." | robots.txt has a `Sitemap:` line. The sitemap is XML (by content type in url mode), and every `<loc>` is on the site's own host. |
| AR-FIND-04 | MAY | "...publish an AI Catalog at `/.well-known/ai-catalog.json` listing every agent-facing resource it ships ... linked from the homepage head with `<link rel="ai-catalog">` and an HTTP `Link` header." | The catalog is valid (see the schema below) and lists `/llms.txt`. The homepage has `<link rel="ai-catalog">`. In url mode the homepage also sends a `Link: <...>; rel="ai-catalog"` header. |
| AR-READ-01 | MUST | "The answer **MUST** be present in the initial HTML — server-rendered or prerendered, not injected by a single-page app after load." | The homepage and each sitemap page return 200 `text/html` with at least `--min-text` characters of visible body text. A page that is byte-identical to the homepage fails. An empty sitemap is a FAIL. |
| AR-READ-02 | MUST | "...accurate HTTP status codes: `404` (or a valid redirect) for missing paths ... never a `200` for a missing page" | url mode: two random `/agentready-probe-<hex>` paths must end, after redirects, on a 404 or 410. dist mode: a `404.html` with text must exist. |
| AR-READ-03 | SHOULD | "The homepage **SHOULD** be served as raw HTML with real links to docs, product, and pricing." | The homepage HTML has at least one `<a href>` to another page on the site. |
| AR-READ-04 | SHOULD | "Docs pages **SHOULD** answer the tasks users bring to agents." | SKIP (manual) |
| AR-READ-05 | SHOULD | "Code snippets **SHOULD** be fenced and language-tagged." | Every `<pre><code>` carries `language-*`, `lang-*` or `data-language`. Every fence in a markdown mirror has an info string. |
| AR-READ-06 | SHOULD | "Discovery files (`llms.txt`, `.well-known/*`, `openapi.json`, `AGENTS.md`) **SHOULD** be linked from content agents already visit" | `/llms.txt` and the catalog (plus `/openapi.json` with `--act`) exist and are linked from the homepage, by `<link>` or `<a>`. |
| AR-READ-07 | SHOULD | "The site **SHOULD** ship an `llms.txt`: a lean, described index of its key pages." | 200 `text/plain` or `text/markdown`, not HTML. It needs an H1 first, a `>` summary, and an `## H2` with a `- [name](url)` list; other prose is allowed. Every on-site link resolves. |
| AR-READ-08 | SHOULD | "Key pages **SHOULD** carry JSON-LD — the homepage above all" | The homepage has a parseable `application/ld+json` block with `@context`. |
| AR-READ-09 | MAY | "Pages **MAY** advertise a markdown mirror via `<link rel="alternate" type="text/markdown">` or an equivalent HTTP `Link:` header." | Every checked page advertises a mirror. The mirror is 200 `text/markdown` or `text/plain`, and is not HTML. |
| AR-READ-10 | n/a | "`AR-READ-10` is retired." | not emitted |
| AR-READ-11 | SHOULD | "Pricing **SHOULD** be published on a first-party page" | SKIP (n/a: no paid plans) |
| AR-ACT-01 | SHOULD | auth completable by an agent; "OAuth 2.0 with discoverable metadata under `/.well-known`" | `--act`: either `oauth-protected-resource` has `resource`, or `oauth-authorization-server` has `issuer`. |
| AR-ACT-02 | SHOULD | "A public API **SHOULD** be described by a machine-readable OpenAPI contract." | `--act`: `/openapi.json` has `openapi` and `paths`, and every operation has an `operationId`. |
| AR-ACT-03 | SHOULD | "...expose an MCP server over Streamable HTTP at `/mcp`." | `--act`, url mode: a POST `initialize` gets a JSON-RPC result, or a 401 with `WWW-Authenticate`. |
| AR-ACT-04 | MAY | "An MCP server **MAY** ship a server card" | `--act`: the catalog has an `application/mcp-server-card+json` entry. |
| AR-ACT-05/06/08/09 | MAY/SHOULD | MCP Apps, SDKs+CLI, payments, NLWeb `/ask` | `--act`: SKIP (manual) |
| AR-ACT-07 | SHOULD | "...register WebMCP tools on `document.modelContext`." | `--act`: `modelContext` appears in the homepage HTML or in its same-site scripts. |
| AR-ACT-10 | MUST | "...**MUST** expose at least one interface an agent can act through: an MCP server (`AR-ACT-03`) or a CLI (`AR-ACT-06`)." | `--act`: same verdict as the `/mcp` probe. |

## kuhy's choices that are stricter than the spec

- Every in-scope item is required, whatever its strength. That includes the
  MAY items (FIND-04, READ-09).
- The spec says a site "**MAY** block a training crawler". kuhy chose to allow
  training crawlers too, so a blanket `Disallow` for GPTBot, ClaudeBot or any
  other agent is a FAIL.
- The act stage is off by default. Turn it on with `--act` only for sites with
  user actions. The spec allows this: "a purely informational site conforms on
  `AR-FIND-*` and `AR-READ-*` alone".

## AI Catalog schema (ai-catalog.md, specVersion 1.0)

- The media type is `application/ai-catalog+json`. When fetched by link
  discovery, plain `application/json` is also acceptable.
- At the top level, the object MUST have:
  - `specVersion`: a string in "Major.Minor" form, for example `"1.0"`.
  - `entries`: an array, which may be empty.
- The top level MAY have `host`, `extensions` and `signature`.
- If `host` is present, it MUST have `displayName`. It MAY have
  `identifier`, `documentationUrl` and `logoUrl`.
- Each entry MUST have:
  - `identifier`: a URI or URN. The recommended form is
    `urn:air:{publisher}:{namespace}:{name}`.
  - `type`: a media type, for example `application/mcp-server-card+json`.
  - **exactly one** of `url` or `data`.
- `displayName` is optional on entries (ai-catalog ADR-0016).
- Link discovery uses `Link: <...>; rel="ai-catalog"` or
  `<link rel="ai-catalog" href="..." type="application/ai-catalog+json">`.

Minimal valid example:

```json
{"specVersion": "1.0",
 "host": {"displayName": "kuhy"},
 "entries": [{"identifier": "urn:air:kuhy.duckdns.org:docs:llms",
              "type": "text/plain", "url": "https://kuhy.duckdns.org/llms.txt"}]}
```

Agentic Resource Discovery v0.91 (<https://agenticresourcediscovery.org/spec>)
renamed the path to `/.well-known/ard.json` and the relation to `rel="ard"`.
It keeps `ai-catalog.json` only as an optional predecessor. AgentReady v2.0
still names `ai-catalog.json`, so that is the path the checker tests. It does
not test `ard.json`.

## llms.txt shape (spec.md, informative)

```md
# Acme
> Acme ships a payments API for developers.

## Docs
- [Quickstart](https://example.com/docs/quickstart): first charge in one request
```
