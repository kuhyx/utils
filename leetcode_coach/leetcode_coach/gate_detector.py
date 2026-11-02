"""Transcript parsing and pasteable-snippet detection for the no-solution gate.

Shared by the Stop hook (`stop_gate.py`) and the offline coach
(`local_coach.py`), so both paths judge a reply with one detector. A snippet
is pasteable when a code span or fenced block uses an identifier from the
problem's starter signature together with a call/spread/assignment -- unless
that exact snippet already appears in kuhy's own messages or the fetched
problem (quoting their code back is fine).

Moved verbatim from ``~/.claude/hooks/leetcode_no_solution_stop.py``.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

_LOG = logging.getLogger(__name__)

KEYWORDS = {
    "function",
    "return",
    "const",
    "let",
    "var",
    "self",
    "def",
    "class",
    "this",
    "new",
    "true",
    "false",
    "null",
    "None",
    "int",
    "str",
    "list",
    "number",
    "string",
    "void",
}
CODE_RE = re.compile(r"```.*?```|`[^`\n]+`", re.DOTALL)
SIG_RE = re.compile(
    r"(?:function\s*(\w*)|def\s+(\w+)|(\w+)\s*=\s*(?:function)?)\s*\(([^)]*)\)"
)
# User-role messages that are not kuhy: the injected skill body and the hook's
# own block reason (which quotes the offending snippet and must not whitelist it).
NOT_KUHY = ("Base directory for this skill", "Stop hook feedback:")
MIN_IDENT_LEN = 2  # single letters (`t`) are too common in prose and toy code
LANG_PREFIXES = ("javascript", "js", "python", "typescript")

Entry = dict[str, Any]


def _parse(line: str) -> object:
    """One JSONL line, or None when it is not JSON (e.g. a half-written tail)."""
    try:
        return json.loads(line)
    except json.JSONDecodeError as exc:
        _LOG.warning("skipping a transcript line that is not JSON: %s", exc)
        return None


def transcript_lines(raw: str) -> list[Entry]:
    """Every JSON object in a JSONL transcript, in order."""
    return [d for d in map(_parse, raw.splitlines()) if isinstance(d, dict)]


def _content(msg: Entry) -> str | list[Entry]:
    """The `message.content` field: a string or a list of content blocks."""
    content: str | list[Entry] = msg.get("message", {}).get("content", "")
    return content


def text_of(msg: Entry) -> str:
    """All text in an entry, tool results included."""
    content = _content(msg)
    if isinstance(content, str):
        return content
    parts = []
    for c in content:
        if c.get("type") == "text":
            parts.append(c.get("text", ""))
        elif c.get("type") == "tool_result":
            inner = c.get("content", "")
            parts.append(
                inner
                if isinstance(inner, str)
                else " ".join(x.get("text", "") for x in inner)
            )
    return "\n".join(parts)


def kuhy_text(msg: Entry) -> str:
    """Only what kuhy typed: no tool results, no skill body, no echoed hook reason."""
    content = _content(msg)
    texts = (
        [content]
        if isinstance(content, str)
        else [c.get("text", "") for c in content if c.get("type") == "text"]
    )
    return "\n".join(t for t in texts if not t.startswith(NOT_KUHY))


def _signature_names(code: str) -> set[str]:
    """Function and parameter names of every signature in `code`."""
    names: set[str] = set()
    for sig in SIG_RE.finditer(code):
        names.update(n for n in sig.groups()[:3] if n)
        for raw in sig.group(4).split(","):
            param = raw.strip().split(":")[0].split("=")[0].strip().lstrip("*")
            if param:
                names.add(param)
    return names


def starter_identifiers(entries: list[Entry]) -> set[str]:
    """Function name + parameter names from the fetched '## Starter code' block."""
    for e in entries:
        if e.get("type") != "user":
            continue
        txt = text_of(e)
        if "## Starter code" not in txt:
            continue
        block = txt.split("## Starter code", 1)[1]
        m = re.search(r"```\n?(.*?)```", block, re.DOTALL)
        code = m.group(1) if m else block
        # LeetCode starters carry the test harness in a block comment; drop
        # comments so its helpers (`log`, `...argsArr`) are not taken as symbols.
        code = re.sub(r"/\*.*?\*/|//[^\n]*|#[^\n]*", "", code, flags=re.DOTALL)
        names = _signature_names(code)
        return {n for n in names if len(n) >= MIN_IDENT_LEN and n not in KEYWORDS}
    return set()


def _squash(text: str) -> str:
    """Collapse every whitespace run to one space."""
    return re.sub(r"\s+", " ", text).strip()


def allowed_text(entries: list[Entry]) -> str:
    """Everything the reply may quote: kuhy's messages and the fetched problem."""
    parts = []
    for e in entries:
        if e.get("type") != "user":
            continue
        parts.append(kuhy_text(e))
        content = _content(e)
        if not isinstance(content, str):
            parts.extend(
                text_of({"message": {"content": [c]}})
                for c in content
                if c.get("type") == "tool_result"
            )
    return _squash("\n".join(parts))


def offending_snippets(reply: str, idents: set[str], allowed: str) -> list[str]:
    """Code in `reply` that uses a starter identifier and is not a quote."""
    bad = []
    for snippet in CODE_RE.findall(reply):
        body = snippet.strip("`").strip()
        if body.startswith(LANG_PREFIXES):
            body = body.split("\n", 1)[1] if "\n" in body else ""
        if not re.search(r"[(=]|\.\.\.", body):
            continue
        if not any(re.search(rf"\b{re.escape(i)}\b", body) for i in idents):
            continue
        probe = _squash(body).removesuffix("...").strip()
        # Whole-token match: the harness has `...argsArr`; it must not admit `...args`.
        if probe and re.search(rf"(?<!\w){re.escape(probe)}(?!\w)", allowed):
            continue  # quoting kuhy's code or the starter back at them
        bad.append(_squash(body)[:80])
    return bad
