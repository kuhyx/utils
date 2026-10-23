#!/usr/bin/env python3
"""Fetch a LeetCode problem statement + starter code as markdown.

Usage: fetch_problem.py <url-or-slug> [--lang javascript]

Uses LeetCode's public GraphQL endpoint (no login). Exit codes:
  0 printed the problem
  1 bad input / network error
  2 problem not available without login (premium) or unknown slug

Stdlib only and free of package imports on purpose: SKILL.md runs it by path
(`python3 ~/.claude/skills/leetcode/fetch_problem.py`), which works without
any install. Its stdout IS its interface (T201 exemption in pyproject.toml).
"""

from __future__ import annotations

import argparse
from html.parser import HTMLParser
import json
import logging
import re
import sys
from typing import Any
import urllib.error
import urllib.request

# A fixed name, and its own NullHandler: run by path this module is
# `__main__` and the package __init__ (which silences the package logger)
# never loads, so without both the warning below would print a second copy of
# the "fetch failed" line through logging's last-resort handler.
_LOG = logging.getLogger("leetcode_coach.fetch_problem")
_LOG.addHandler(logging.NullHandler())

GRAPHQL = "https://leetcode.com/graphql"
QUERY = """
query q($s: String!) {
  question(titleSlug: $s) {
    questionFrontendId title difficulty content isPaidOnly
    codeSnippets { langSlug code }
    topicTags { name }
    hints
  }
}
"""
EXIT_FAILED, EXIT_UNAVAILABLE = 1, 2
_OPEN = {"p": "\n", "div": "\n", "ul": "\n", "ol": "\n", "li": "\n- ", "br": "\n"}
_CLOSE = {"p": "\n", "div": "\n"}
_BOTH = {"strong": "**", "b": "**", "em": "_", "i": "_"}


class _HtmlToText(HTMLParser):
    """Minimal HTML -> markdown-ish text; keeps <pre>/<code> verbatim."""

    def __init__(self) -> None:
        super().__init__()
        self.out: list[str] = []
        self.in_pre = False
        self.in_code = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Open a fence, an inline code span or a markdown marker."""
        del attrs  # no attribute matters for the text
        if tag == "pre":
            self.in_pre = True
            self.out.append("\n```\n")
        elif tag == "code" and not self.in_pre:
            self.in_code = True
            self.out.append("`")
        elif tag in _OPEN or tag in _BOTH:
            self.out.append(_OPEN.get(tag) or _BOTH[tag])

    def handle_endtag(self, tag: str) -> None:
        """Close what `handle_starttag` opened."""
        if tag == "pre":
            self.in_pre = False
            self.out.append("\n```\n")
        elif tag == "code" and self.in_code:
            self.in_code = False
            self.out.append("`")
        elif tag in _CLOSE or tag in _BOTH:
            self.out.append(_CLOSE.get(tag) or _BOTH[tag])

    def handle_data(self, data: str) -> None:
        """Text: verbatim inside <pre>, whitespace-collapsed elsewhere."""
        self.out.append(data if self.in_pre else re.sub(r"\s+", " ", data))

    def text(self) -> str:
        """Everything fed so far, with runs of blank lines squeezed."""
        return re.sub(r"\n{3,}", "\n\n", "".join(self.out)).strip()


def slug_from(arg: str) -> str:
    """Accept a full URL (with /description/, /submissions/, ?query) or a bare slug."""
    m = re.search(r"leetcode\.(?:com|cn)/problems/([a-z0-9-]+)", arg)
    if m:
        return m.group(1)
    if re.fullmatch(r"[a-z0-9-]+", arg):
        return arg
    msg = f"not a LeetCode problem URL or slug: {arg!r}"
    raise ValueError(msg)


def fetch(slug: str) -> dict[str, Any] | None:
    """The GraphQL `question` object for `slug`, or None when LeetCode has none."""
    body = json.dumps({"query": QUERY, "variables": {"s": slug}}).encode()
    req = urllib.request.Request(
        GRAPHQL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Referer": f"https://leetcode.com/problems/{slug}/",
            "User-Agent": "Mozilla/5.0 (leetcode-coach skill)",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:  # fixed https URL
        payload = json.load(resp)
    question: dict[str, Any] | None = payload.get("data", {}).get("question")
    return question


def render(q: dict[str, Any], lang: str) -> str:
    """Markdown: title, tags, statement, starter code, then the hidden hints."""
    parser = _HtmlToText()
    parser.feed(q["content"] or "")
    tags = ", ".join(t["name"] for t in q["topicTags"]) or "none"
    snippets = {s["langSlug"]: s["code"] for s in q["codeSnippets"]}
    chosen = lang if lang in snippets else next(iter(snippets), None)
    lines = [
        f"# {q['questionFrontendId']}. {q['title']} ({q['difficulty']})",
        f"Tags: {tags}",
        f"Languages available: {', '.join(snippets) or 'none'}",
        "",
        parser.text(),
        "",
    ]
    if chosen:
        lines += [
            f"## Starter code ({chosen})",
            "```",
            snippets[chosen].rstrip(),
            "```",
        ]
    if q["hints"]:
        lines += ["", "## Site hints (do NOT show to the user unasked)"]
        lines += [f"- {h}" for h in q["hints"]]
    return "\n".join(lines)


def main() -> int:
    """Print the problem named on argv; see the module docstring for exit codes."""
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("problem", help="LeetCode problem URL or title slug")
    ap.add_argument("--lang", default="javascript", help="starter-code language slug")
    args = ap.parse_args()
    try:
        slug = slug_from(args.problem)
        q = fetch(slug)
    except (
        ValueError,
        urllib.error.URLError,
        TimeoutError,
        json.JSONDecodeError,
    ) as exc:
        _LOG.warning("fetch failed: %s", exc)
        print(f"fetch failed: {exc}", file=sys.stderr)
        return EXIT_FAILED
    if q is None or q.get("isPaidOnly") or not q.get("content"):
        print(
            f"problem {slug!r} is unknown or premium-only (no statement without login)",
            file=sys.stderr,
        )
        return EXIT_UNAVAILABLE
    print(render(q, args.lang))
    return 0


if __name__ == "__main__":
    sys.exit(main())
