from __future__ import annotations

from dataclasses import dataclass
import re

from code_runner._model import RunnerError
from code_runner._split import split_top_level

_IDENT = r"[A-Za-z_$][\w$]*"
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"^\s*(?://|#).*$", re.MULTILINE)
_PY_CLASS = re.compile(r"^class\s+(\w+)", re.MULTILINE)
_PY_DEF = re.compile(r"\bdef\s+(?!__)(\w+)\s*\(")
_PY_FUNC = re.compile(r"^def\s+(\w+)\s*\(", re.MULTILINE)
_JS_CLASS = re.compile(rf"^\s*class\s+({_IDENT})", re.MULTILINE)
_JS_METHOD = re.compile(
    rf"^\s+(?:async\s+)?(?!constructor\b)({_IDENT})\s*\(", re.MULTILINE
)
_JS_ASSIGNED = re.compile(
    rf"\b(?:var|let|const)\s+({_IDENT})\s*(?::[^=]+)?=\s*(?:async\s+)?(?:function\b\s*\w*\s*)?\("
)
_JS_DECLARED = re.compile(rf"\bfunction\s+({_IDENT})\s*\(")
_NOT_METHODS = {"if", "for", "while", "switch", "catch", "return", "function"}


@dataclass(frozen=True)
class Entry:
    cls: str | None
    name: str
    params: tuple[str, ...]


def _no_entry(lang: str) -> RunnerError:
    return RunnerError(f"no entry point found in the {lang} starter code")


def _balanced(text: str, open_at: int) -> str:
    depth = 0
    for i in range(open_at, len(text)):
        ch = text[i]
        if ch in "([{" or (ch == "<" and depth > 0):
            depth += 1
        elif ch in ")]}" or (ch == ">" and text[i - 1] != "=" and depth > 1):
            depth -= 1
            if depth == 0:
                return text[open_at + 1 : i]
    return text[open_at + 1 :]


def _params(code: str, open_at: int) -> tuple[str, ...]:
    names: list[str] = []
    for part in split_top_level(_balanced(code, open_at)):
        found = re.match(_IDENT, part.strip())
        if found:
            names.append(found.group())
    return tuple(names)


def _python(text: str) -> Entry | None:
    code = _LINE_COMMENT.sub("", text)
    owner = _PY_CLASS.search(code)
    if owner is None:
        found = _PY_FUNC.search(code)
        return found and Entry(None, found.group(1), _params(code, found.end() - 1))
    found = _PY_DEF.search(code, owner.end())
    if found is None:
        return None
    params = _params(code, found.end() - 1)
    return Entry(
        owner.group(1), found.group(1), tuple(p for p in params if p != "self")
    )


def _javascript(text: str) -> Entry | None:
    code = _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", text))
    owner = _JS_CLASS.search(code)
    if owner is not None:
        for method in _JS_METHOD.finditer(code, owner.end()):
            if method.group(1) not in _NOT_METHODS:
                return Entry(
                    owner.group(1), method.group(1), _params(code, method.end() - 1)
                )
        return None
    found = _JS_ASSIGNED.search(code) or _JS_DECLARED.search(code)
    return found and Entry(None, found.group(1), _params(code, found.end() - 1))


def parse_starter(lang: str, text: str) -> Entry:
    entry = _python(text) if lang == "python3" else _javascript(text)
    if entry is None:
        raise _no_entry(lang)
    return entry


def extract_starter(statement: str) -> str:
    lines = statement.splitlines(keepends=True)
    heads = [i for i, line in enumerate(lines) if line.startswith("## Starter code")]
    if not heads:
        return ""
    body = lines[heads[0] + 1 :]
    if body and body[0].startswith("```"):
        body = body[1:]
        end = next(
            (i for i, line in enumerate(body) if line.startswith("```")), len(body)
        )
        return "".join(body[:end])
    end = next((i for i, line in enumerate(body) if line.startswith("## ")), len(body))
    return "".join(body[:end])
