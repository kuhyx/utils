# Copyright (c) 2026 Krzysztof Rudnicki
"""Group error reports: one signature per bug, however often it fires.

Ported from kartka's ``tools/errors`` (``kartka_errors.signature``) and kept
byte-identical for Dart entries, so kartka's existing tickets keep their ids
when it moves onto this ingest. Generalised in one place only: which stack
frames belong to the app. An entry's ``mark`` names them (``package:todo/``
for Dart, ``leetcode_guard/`` for Python, ``res://`` for GDScript); without
one it is ``package:<app>/``.

A signature is the error type, the message with its volatile parts (numbers,
ids, URLs) masked, and where it happened: the first app frame without line
numbers (so an edit elsewhere in the file does not split it), else the route,
else the entry kind. A slow wait is its route + operation, never its time.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

#: The longest normalised message kept in a signature.
MAX_MESSAGE = 160
#: The entry kind of a user-visible wait over a second.
SLOW_KIND = "perf.slow"

_TYPE = re.compile(r"^(?:Unhandled error: )?([A-Z][\w$]*(?:Exception|Error))\b")
#: Dart errors whose ``toString`` does not name their type.
_DART_PREFIXES = {
    "Bad state": "StateError",
    "Invalid argument": "ArgumentError",
    "Unsupported operation": "UnsupportedError",
    "Null check operator": "TypeError",
    "Concurrent modification": "ConcurrentModificationError",
}
_URL = re.compile(r"(https?://\S+|<url>)")
_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE)
_HEX = re.compile(r"\b(?=[0-9a-f]*\d)[0-9a-f]{8,}\b", re.IGNORECASE)
_NUMBER = re.compile(r"\b\d+(\.\d+)?\b")
_SPACE = re.compile(r"\s+")
_FRAME = re.compile(r"^#\d+\s+")
_LINE_COL = re.compile(r"(\.(?:dart|py|gd))(:\d+)+")
#: Frames of the reporting plumbing itself, never the bug's location.
_PLUMBING = (
    "package:kartka/app/error_hooks.dart",
    "package:kartka/core/diagnostics/",
    "package:crdt_sync_flutter/src/errors/",
    "gatelock/error_report.py",
    "res://addons/app_errors/",
)


@dataclass(frozen=True)
class Signature:
    """What groups reports of one bug."""

    id: str
    type: str
    message: str
    where: str


def error_type(error: str, kind: str) -> str:
    """Return the exception type named by ``error``, else ``kind``."""
    if match := _TYPE.match(error):
        return match[1]
    for prefix, name in _DART_PREFIXES.items():
        if error.startswith(prefix):
            return name
    return kind


def normalise(message: str) -> str:
    """Return ``message`` with URLs, uuids, long hex and numbers masked, trimmed."""
    text = _URL.sub("<url>", message)
    text = _UUID.sub("<uuid>", text)
    text = _HEX.sub("<hex>", text)
    text = _NUMBER.sub("<n>", text)
    return _SPACE.sub(" ", text).strip()[:MAX_MESSAGE]


def top_frame(stack: Sequence[str], mark: str) -> str | None:
    """Return the first frame containing ``mark`` outside the reporting plumbing."""
    for frame in stack:
        if mark in frame and not any(p in frame for p in _PLUMBING):
            return _LINE_COL.sub(r"\1", _FRAME.sub("", frame.strip()))
    return None


def mark_of(entry: Mapping[str, object], app: str) -> str:
    """Return the substring that marks the app's own frames in ``entry``."""
    mark = entry.get("mark")
    return mark if isinstance(mark, str) and mark else f"package:{app}/"


def strings(value: object) -> list[str]:
    """Return ``value`` as a list of strings; empty when it is not a list."""
    return [str(v) for v in value] if isinstance(value, list) else []


def _digest(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:10]  # noqa: S324 -- a grouping key, not security


def signature(entry: Mapping[str, object], *, app: str) -> Signature:
    """Return the signature of one report of ``app``."""
    kind = str(entry.get("kind", "?"))
    if kind == SLOW_KIND:
        operation = str(entry.get("operation") or "?")
        where = f"route {entry.get('route') or '?'}"
        return Signature(
            _digest(f"{SLOW_KIND}|{where}|{operation}"),
            SLOW_KIND,
            f"slow wait: {operation}",
            where,
        )
    error = str(entry.get("error", ""))
    frame = top_frame(strings(entry.get("stack")), mark_of(entry, app))
    route = entry.get("route")
    where = frame or (f"route {route}" if route else f"kind {kind}")
    kind_type = error_type(error, kind)
    message = normalise(error)
    return Signature(_digest(f"{kind_type}|{message}|{where}"), kind_type, message, where)
