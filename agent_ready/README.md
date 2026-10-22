# agent_ready

This tool checks kuhy's websites against [AgentReady](https://agentready.org)
v2.0. It runs every find and read item, and the act items when you pass `--act`.
It is Python 3 standard library only, with no dependencies.
`DOCS-spec-notes.md` maps each `AR-*` ID to the check that tests it.

## Usage

```sh
~/src/utils/agent_ready/check.sh dist <build-dir> [--act] [--min-text N] [--max-pages N]
~/src/utils/agent_ready/check.sh url  <base-url>  [--act] [--min-text N] [--max-pages N] [--timeout S] [--budget S]
```

The output is one line per check:

```text
PASS AR-FIND-03 sitemap lists 12 pages
FAIL AR-READ-02 soft 404, unknown paths must return 404: /agentready-probe-1a2b -> HTTP 200
SKIP AR-READ-11 pricing page: n/a for sites without paid plans
```

| exit | meaning |
|---|---|
| 0 | every check passed (SKIPs do not fail) |
| 1 | at least one FAIL, at any strength: MUST, SHOULD or MAY |
| 2 | usage error (bad arguments, missing directory, not an http(s) URL) |
| 3 | network undeterminable: the homepage was unreachable, or a fetch timed out or hit the 45 s budget, and nothing failed |

## Pre-commit and CI (dist mode)

Point the checker at the build output after the build step. Dist mode checks
that each file exists and is well-formed:

- robots.txt
- sitemap.xml
- llms.txt
- the AI Catalog
- 404.html
- the text in every sitemap page's HTML
- each page's markdown mirror

```yaml
# .github/workflows/*.yml, after the build
- run: ~/src/utils/agent_ready/check.sh dist dist/
```

```yaml
# .pre-commit-config.yaml (local hook; build first, e.g. in a wrapper script)
- id: agent-ready
  name: AgentReady (build output)
  entry: bash -c 'pnpm build >/dev/null && ~/src/utils/agent_ready/check.sh dist dist'
  language: system
  pass_filenames: false
```

Dist mode cannot check HTTP behaviour: content types, the `Link` header, real
404 status, or responses to agent user-agents. Those checks print as SKIP, or
the check falls back to "404.html exists".

## Post-deploy (url mode)

Run this once the deploy is live:

```sh
~/src/utils/agent_ready/check.sh url https://kuhy.duckdns.org
```

Url mode checks status codes **and** content types. A server that answers
every path with `200 text/html` (an SPA fallback) fails on robots.txt, the
sitemap, llms.txt, the catalog and the 404 probe. A status-only check would
pass it. Url mode also checks that:

- `/agentready-probe-<random>` ends on a 404, after following redirects.
- No sitemap page is byte-identical to the homepage shell.
- The homepage answers 200 to ClaudeBot, GPTBot and the other agent
  user-agents.

## Tests

```sh
~/.claude/scripts/capped.sh python -m pytest ~/src/utils/agent_ready/tests -q
```

The test fixtures are generated in `tmp_path` by `tests/sitegen.py`, so there
are no static mirror `.md` files to trip the markdown-naming gate. The good
and bad build trees are served by loopback `http.server` instances in four
shapes:

- compliant
- SPA fallback
- JSON 404 on every path
- 403 to GPTBot
