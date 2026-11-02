from __future__ import annotations

_OPEN = "([{<"
_CLOSE = ")]}>"


def split_top_level(text: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    quote = ""
    escaped = False
    start = 0
    for i, ch in enumerate(text):
        if escaped:
            escaped = False
        elif quote:
            escaped = ch == "\\"
            quote = "" if ch == quote else quote
        elif ch in "\"'":
            quote = ch
        elif ch in _OPEN:
            depth += 1
        elif ch in _CLOSE and not (ch == ">" and text[i - 1] in "=-"):
            depth = max(depth - 1, 0)
        elif ch == "," and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return [part.strip() for part in parts]
